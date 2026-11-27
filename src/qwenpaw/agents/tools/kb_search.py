# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=line-too-long
"""Organization knowledge-base search for BeeAgent Hub runtimes."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from agentscope.message import TextBlock, ToolResultState
from agentscope.tool import ToolChunk

from ...runtime.tool_registry import tool_descriptor

logger = logging.getLogger(__name__)


def _make_response(text: str, *, ok: bool = True) -> ToolChunk:
    return ToolChunk(
        is_last=True,
        state=ToolResultState.SUCCESS if ok else ToolResultState.ERROR,
        content=[TextBlock(type="text", text=text)],
    )


def _format_hits(query: str, hits: list[dict]) -> str:
    if not hits:
        return (
            f'No org-KB hits for "{query}". '
            "Try different keywords, or ask the user to upload docs in Console → 知识库."
        )
    lines = [f'Org knowledge hits for "{query}" ({len(hits)}):', ""]
    for index, hit in enumerate(hits, start=1):
        kb_name = hit.get("kb_name") or hit.get("kb_slug") or "kb"
        kb_slug = hit.get("kb_slug") or ""
        title = hit.get("title") or "untitled"
        snippet = (
            hit.get("snippet") or hit.get("body") or hit.get("text") or ""
        ).strip()
        if len(snippet) > 600:
            snippet = snippet[:600].rstrip() + "…"
        cite = f"[{index}] {kb_name}"
        if kb_slug:
            cite += f" ({kb_slug})"
        cite += f" · {title}"
        cust = hit.get("customer_key") or ""
        if cust:
            cite += f" · customer:{cust}"
        doc_id = hit.get("doc_id") or ""
        if doc_id:
            cite += f" · doc:{doc_id}"
        lines.append(cite)
        lines.append(snippet)
        lines.append("")
    lines.append(
        "When answering, cite these org-KB sources by title "
        "(and kb name). Do not invent quotes beyond the snippets."
    )
    return "\n".join(lines).rstrip() + "\n"


def _user_may_search(database_path: Path, user_id: str) -> bool:
    """Return True when the Hub user holds org_kb:use (or is admin)."""
    if not user_id:
        # Provisioned same-host runtime without user id — allow read for MVP.
        return True
    try:
        from ...hub.rbac.catalog import PERM_ORG_KB_USE, matches_permission
        from ...hub.rbac.service import RbacService

        rbac = RbacService(database_path)
        ent = rbac.entitlements(user_id, is_hub_admin=False)
        if ent.get("is_hub_admin"):
            return True
        perms = set(ent.get("permissions") or [])
        return matches_permission(perms, PERM_ORG_KB_USE)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("kb_search ACL check failed: %s", exc)
        return False


@tool_descriptor(
    async_execution=True,
    tool_type="internal",
    target_param="query",
    policy_name="KbSearch",
    default_policy="allow",
    policy_reason="Allow organization knowledge-base search",
    ui_description="Search organization knowledge bases (口径/案例/模板…)",
    ui_icon="📚",
)
def _user_bypasses_customer_acl(database_path: Path, user_id: str) -> bool:
    """True when Hub admin or org_kb:manage — can see all customer-tagged docs."""
    if not user_id:
        return False
    try:
        from ...hub.rbac.catalog import PERM_ORG_KB_MANAGE, matches_permission
        from ...hub.rbac.service import RbacService

        rbac = RbacService(database_path)
        ent = rbac.entitlements(user_id, is_hub_admin=False)
        if ent.get("is_hub_admin"):
            return True
        perms = set(ent.get("permissions") or [])
        return matches_permission(perms, PERM_ORG_KB_MANAGE)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("kb_search customer ACL check failed: %s", exc)
        return False


async def kb_search(
    query: str,
    kb_slug: Optional[str] = None,
    skill: Optional[str] = None,
    customer_key: Optional[str] = None,
    as_of: Optional[str] = None,
    limit: int = 8,
) -> ToolChunk:
    """Search BeeAgent organization knowledge bases and return citable snippets.

    Use this before drafting 口径 / 网评 / 申诉 / 报告 when org-approved facts,
    past cases, or templates may already exist. Prefer this over inventing
    internal policy. Still use web_search for public news and regulations.

    Args:
        query: Search keywords or a short question in Chinese or English.
        kb_slug: Optional library slug — ``koujing`` (口径库), ``case`` (案例库),
            ``template`` (模板资产库), ``customer`` (客户资料库). Takes precedence
            over ``skill`` bindings when set.
        skill: Optional skill name (e.g. ``koujing-xiezhuan``). When set and
            ``kb_slug`` is omitted, search only Hub-bound libraries for that
            skill (Console → 知识库 → Skill 绑定).
        customer_key: Optional customer tag (e.g. ``acme``). Limits results to
            that customer's docs. Untagged org docs remain visible; tagged docs
            outside the caller's grants are never returned (anti cross-client).
        as_of: Optional date ``YYYY-MM-DD`` for historical recall. Defaults to
            today; expired / not-yet-effective docs are excluded.
        limit: Max snippets (1–20, default 8).

    Returns:
        `ToolChunk`: Ranked snippets with library name, document title, and
        ``doc_id`` for citation.
    """
    needle = (query or "").strip()
    if not needle:
        return _make_response("Error: query is empty.", ok=False)

    db_env = (os.environ.get("QWENPAW_HUB_CONTROL_DB") or "").strip()
    if not db_env:
        return _make_response(
            "Organization knowledge base is not configured for this runtime "
            "(missing QWENPAW_HUB_CONTROL_DB). Ask the user to use Hub Console "
            "知识库, or continue with workspace files / web_search.",
            ok=False,
        )

    database_path = Path(db_env).expanduser()
    if not database_path.is_file():
        return _make_response(
            f"Hub control database not found: {database_path}",
            ok=False,
        )

    user_id = (os.environ.get("QWENPAW_HUB_USER_ID") or "").strip()
    if not _user_may_search(database_path, user_id):
        return _make_response(
            "Permission denied: missing org_kb:use. Ask an admin to grant "
            "organization knowledge-base access.",
            ok=False,
        )

    try:
        from ...hub.org_kb.service import OrgKbService

        service = OrgKbService(database_path)
        service.ensure_default_libraries(created_by=user_id or "system")
        capped = max(1, min(int(limit or 8), 20))
        slug = (kb_slug or "").strip() or None
        skill_name = (skill or "").strip().lower() or None
        cust = (customer_key or "").strip().lower() or None
        as_of_day = (as_of or "").strip() or None
        hits = service.search(
            query=needle,
            kb_slug=slug,
            skill_name=None if slug else skill_name,
            customer_key=cust,
            user_id=user_id,
            bypass_acl=_user_bypasses_customer_acl(database_path, user_id),
            as_of=as_of_day,
            limit=capped,
        )
        return _make_response(_format_hits(needle, hits))
    except KeyError as exc:
        return _make_response(str(exc), ok=False)
    except ValueError as exc:
        return _make_response(str(exc), ok=False)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("kb_search failed: %s", exc)
        return _make_response(f"kb_search failed: {exc}", ok=False)
