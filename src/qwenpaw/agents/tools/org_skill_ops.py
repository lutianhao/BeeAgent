# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=line-too-long
"""Org skill market + local enable/disable tools for BeeAgent Hub runtimes."""

from __future__ import annotations

import io
import json
import logging
import os
import zipfile
from pathlib import Path

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


def _hub_db() -> Path | None:
    raw = (os.environ.get("QWENPAW_HUB_CONTROL_DB") or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_file() else None


def _hub_user_id() -> str:
    return (os.environ.get("QWENPAW_HUB_USER_ID") or "").strip()


def _hub_username(database_path: Path, user_id: str) -> str:
    """Resolve a display username for org-skill ownership attribution."""
    env_name = (os.environ.get("QWENPAW_HUB_USERNAME") or "").strip()
    if env_name:
        return env_name
    if not user_id:
        return "hub-user"
    try:
        import sqlite3

        with sqlite3.connect(str(database_path)) as connection:
            row = connection.execute(
                "SELECT username FROM hub_users WHERE user_id = ? LIMIT 1",
                (user_id,),
            ).fetchone()
        if row and row[0]:
            return str(row[0]).strip()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("resolve hub username failed: %s", exc)
    return user_id


def _permission_set(database_path: Path, user_id: str) -> set[str]:
    if not user_id:
        return set()
    try:
        from ...hub.rbac.service import RbacService

        rbac = RbacService(database_path)
        ent = rbac.entitlements(user_id, is_hub_admin=False)
        if ent.get("is_hub_admin"):
            return {"*"}
        return set(ent.get("permissions") or [])
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("org skill ops RBAC failed: %s", exc)
        return set()


def _has_perm(database_path: Path, user_id: str, needed: str) -> bool:
    from ...hub.rbac.catalog import matches_permission

    return matches_permission(_permission_set(database_path, user_id), needed)


def _agent_workspace_dir() -> Path | None:
    """Resolve the agent workspace that owns ``skills/`` + ``skill.json``."""
    try:
        from ...constant import WORKING_DIR
    except Exception:  # pylint: disable=broad-exception-caught
        raw = (os.environ.get("QWENPAW_WORKING_DIR") or "").strip()
        if not raw:
            return None
        root = Path(raw).expanduser()
    else:
        root = Path(WORKING_DIR)
    if (root / "skill.json").is_file() and (root / "skills").exists():
        return root
    default = root / "workspaces" / "default"
    if (default / "skill.json").is_file() or (default / "skills").exists():
        return default
    if default.exists():
        return default
    return None


def _zip_skill_dir(skill_dir: Path) -> tuple[str, bytes]:
    """Build ``<name>/...`` zip bytes from a skill directory."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise ValueError(f"SKILL.md not found under {skill_dir}")
    name = skill_dir.name.strip().lower()
    if not name:
        raise ValueError("skill directory name is empty")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(skill_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.name in {"__pycache__", ".DS_Store", "Thumbs.db"}:
                continue
            if "__pycache__" in path.parts or ".git" in path.parts:
                continue
            arc = f"{name}/{path.relative_to(skill_dir).as_posix()}"
            zf.write(path, arc)
    return name, buf.getvalue()


def _resolve_skill_id(service, skill_id: str = "", name: str = "") -> str:
    sid = (skill_id or "").strip()
    if sid:
        return sid
    needle = (name or "").strip().lower()
    if not needle:
        raise ValueError("Provide skill_id or name")
    items = service.list_visible(is_hub_member=True, user_id=_hub_user_id())
    for item in items:
        if str(item.get("name") or "").lower() == needle:
            return str(item["skill_id"])
        if str(item.get("skill_id") or "") == needle:
            return str(item["skill_id"])
    raise KeyError(f"组织技能不存在：{needle}")


@tool_descriptor(
    async_execution=True,
    tool_type="internal",
    target_param="skill_dir",
    policy_name="OrgSkillPublish",
    default_policy="allow",
    policy_reason="Publish workspace skill package to organization market",
    ui_description="Publish a local skill directory to the org skill market",
    ui_icon="📤",
)
async def org_skill_publish(
    skill_dir: str,
    version_text: str = "",
    changelog: str = "",
    category: str = "other",
    visibility: str = "personal",
    display_name: str = "",
    description: str = "",
) -> ToolChunk:
    """Publish a local Skill directory to the BeeAgent organization market.

    Use only when the user **explicitly** asks to upload / publish to the
    organization skill shelf (组织技能市场). Requires ``org_skill:publish``.
    The directory must contain ``SKILL.md`` (agentskills layout).

    Args:
        skill_dir: Absolute path to the skill package directory (has SKILL.md).
        version_text: Optional version (e.g. ``1.1.0``). Empty = auto bump.
        changelog: What changed in this version (recommended for updates).
        category: business domain — ``koujing`` / ``yuqing`` / ``appeal`` /
            ``report`` / ``drill`` / ``data`` / ``tools`` / ``content`` /
            ``ops`` / ``finance`` / ``other``.
        visibility: ``personal`` (default, only you) / ``org`` / ``public``.
            Ask before listing to org if the user said「上架到组织」.
        display_name: Optional display title override.
        description: Optional description override (must include use-when hint).

    Returns:
        Publish result with skill_id, name, version, and whether it was an update.
    """
    db = _hub_db()
    if db is None:
        return _make_response(
            "Organization skill market is not configured "
            "(missing QWENPAW_HUB_CONTROL_DB). Use Console → Market instead.",
            ok=False,
        )
    user_id = _hub_user_id()
    from ...hub.rbac.catalog import PERM_ORG_SKILL_PUBLISH

    if not _has_perm(db, user_id, PERM_ORG_SKILL_PUBLISH):
        return _make_response(
            "Permission denied: missing org_skill:publish. "
            "Ask an admin to grant publish rights, or upload via Console Market.",
            ok=False,
        )

    root = Path(skill_dir).expanduser().resolve()
    if not root.is_dir():
        return _make_response(f"skill_dir is not a directory: {root}", ok=False)

    try:
        _name, zip_bytes = _zip_skill_dir(root)
        from ...hub.org_skills.service import OrgSkillsService

        service = OrgSkillsService(db)
        username = _hub_username(db, user_id)
        result = service.publish_from_zip(
            zip_bytes=zip_bytes,
            visibility=(visibility or "personal").strip() or "personal",
            display_name=(display_name or "").strip(),
            description=(description or "").strip(),
            # Empty version → service auto patch-bumps on update / 1.0.0 on create.
            # Do not default to "1.0" here or updates never bump.
            version_text=(version_text or "").strip(),
            changelog=(changelog or "").strip(),
            category=(category or "other").strip() or "other",
            owner_user_id=user_id or "unknown",
            owner_username=username,
        )
        is_update = bool(result.get("is_update"))
        display = (
            str(result.get("display_name") or "").strip()
            or str(result.get("name") or "")
        )
        vis = str(result.get("visibility") or "personal")
        vis_label = {
            "personal": "个人（仅自己可见，未上组织货架）",
            "org": "组织内部",
            "public": "公开",
        }.get(vis, vis)
        lines = [
            "已发布到技能货架。",
            f"- 显示名: {display}",
            f"- 英文名: {result.get('name')}",
            f"- skill_id: {result.get('skill_id')}",
            f"- 版本: {result.get('version_text')}",
            f"- 更新: {'是（新版本）' if is_update else '否（新建）'}",
            f"- 可见性: {vis_label}",
        ]
        if result.get("compatibility"):
            lines.append(f"- compatibility: {result.get('compatibility')}")
        tools = result.get("allowed_tools") or []
        if tools:
            lines.append(f"- allowed_tools: {', '.join(tools)}")
        if vis == "personal":
            lines.append(
                "当前仅你可见。若要同事安装，请在市场详情点「上架到组织」，"
                "或让我帮你把 visibility 改为 org。"
            )
        else:
            lines.append(
                "查看路径：扩展 / 市场 → 技能 → 组织技能"
                "（/market?tab=skills&source=beeagent-org）。"
            )
        return _make_response("\n".join(lines))
    except ValueError as exc:
        return _make_response(str(exc), ok=False)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("org_skill_publish failed: %s", exc)
        return _make_response(f"org_skill_publish failed: {exc}", ok=False)


@tool_descriptor(
    async_execution=True,
    tool_type="internal",
    target_param="name",
    policy_name="OrgSkillInstall",
    default_policy="allow",
    policy_reason="Install org market skill into personal runtime",
    ui_description="Install an organization market skill into this runtime",
    ui_icon="📥",
)
async def org_skill_install(
    name: str = "",
    skill_id: str = "",
    force: bool = False,
) -> ToolChunk:
    """Install (or upgrade) an organization market skill into this Hub runtime.

    Args:
        name: Skill technical name (e.g. ``koujing-xiezhuan``).
        skill_id: Optional Hub skill_id (wins over name when both set).
        force: If pinned and a newer version exists, force upgrade keeping pin.

    Returns:
        Install confirmation with version.
    """
    db = _hub_db()
    if db is None:
        return _make_response(
            "Organization skill market is not configured "
            "(missing QWENPAW_HUB_CONTROL_DB).",
            ok=False,
        )
    user_id = _hub_user_id()
    if not user_id:
        return _make_response(
            "Missing QWENPAW_HUB_USER_ID — cannot install for a Hub user.",
            ok=False,
        )
    try:
        from ...hub.org_skills.service import OrgSkillsService

        service = OrgSkillsService(db)
        sid = _resolve_skill_id(service, skill_id=skill_id, name=name)
        result = service.install_for_user(
            sid,
            user_id=user_id,
            is_hub_member=True,
            force=bool(force),
            granted_permissions=_permission_set(db, user_id),
        )
        return _make_response(
            "Installed org skill into this runtime.\n"
            f"- name: {result.get('name')}\n"
            f"- version: {result.get('version_text')}\n"
            f"- pinned: {result.get('pinned')}\n"
            "Use skill_set_enabled to enable/disable auto-activation.",
        )
    except KeyError as exc:
        return _make_response(str(exc), ok=False)
    except ValueError as exc:
        return _make_response(str(exc), ok=False)
    except RuntimeError as exc:
        return _make_response(str(exc), ok=False)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("org_skill_install failed: %s", exc)
        return _make_response(f"org_skill_install failed: {exc}", ok=False)


@tool_descriptor(
    async_execution=True,
    tool_type="internal",
    target_param="name",
    policy_name="OrgSkillPin",
    default_policy="allow",
    policy_reason="Pin or unpin installed org skill version",
    ui_description="Pin/unpin the installed version of an org skill",
    ui_icon="📌",
)
async def org_skill_pin(
    pinned: bool,
    name: str = "",
    skill_id: str = "",
) -> ToolChunk:
    """Pin or unpin the installed version of an organization skill.

    When pinned, upgrade prompts are suppressed until the user unpins
    (or installs with force=true).

    Args:
        pinned: True to pin, False to unpin.
        name: Skill technical name.
        skill_id: Optional Hub skill_id.
    """
    db = _hub_db()
    if db is None:
        return _make_response(
            "Organization skill market is not configured.",
            ok=False,
        )
    user_id = _hub_user_id()
    if not user_id:
        return _make_response("Missing QWENPAW_HUB_USER_ID.", ok=False)
    try:
        from ...hub.org_skills.service import OrgSkillsService

        service = OrgSkillsService(db)
        sid = _resolve_skill_id(service, skill_id=skill_id, name=name)
        result = service.set_pin_for_user(
            sid,
            user_id=user_id,
            pinned=bool(pinned),
            is_hub_member=True,
        )
        state = "pinned" if result.get("pinned") else "unpinned"
        return _make_response(
            f"Org skill {result.get('name')} is now {state}.\n"
            f"- installed_version: {result.get('installed_version')}\n"
            f"- update_available: {result.get('update_available')}\n"
            f"- newer_version: {result.get('newer_version') or '-'}",
        )
    except KeyError as exc:
        return _make_response(str(exc), ok=False)
    except ValueError as exc:
        return _make_response(str(exc), ok=False)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("org_skill_pin failed: %s", exc)
        return _make_response(f"org_skill_pin failed: {exc}", ok=False)


@tool_descriptor(
    async_execution=True,
    tool_type="internal",
    target_param="skill_name",
    policy_name="SkillSetEnabled",
    default_policy="allow",
    policy_reason="Enable or disable a local workspace skill",
    ui_description="Enable or disable a skill in this agent workspace",
    ui_icon="🔀",
)
async def skill_set_enabled(
    skill_name: str,
    enabled: bool,
) -> ToolChunk:
    """Enable or disable a skill in the current agent workspace.

    Disabled skills stay installed but are not auto-selected; the user can
    still force them with ``/`` or ``@``. Prefer this over uninstalling.

    Args:
        skill_name: Technical skill directory name.
        enabled: True to enable, False to disable.
    """
    name = (skill_name or "").strip()
    if not name:
        return _make_response("skill_name is required.", ok=False)
    workspace = _agent_workspace_dir()
    if workspace is None:
        return _make_response(
            "Could not resolve agent workspace (skills/). "
            "Use Console → Market → 已安装专项 instead.",
            ok=False,
        )
    try:
        from ...agents.skill_system.workspace_service import SkillService
        from ...exceptions import SkillScanError

        svc = SkillService(workspace)
        if enabled:
            try:
                result = svc.enable_skill(name)
            except SkillScanError as exc:
                return _make_response(f"Enable blocked by scan: {exc}", ok=False)
        else:
            result = svc.disable_skill(name)
        if not result.get("success"):
            reason = result.get("reason") or "not_found"
            return _make_response(
                f"Failed to {'enable' if enabled else 'disable'} "
                f"'{name}': {reason}",
                ok=False,
            )
        return _make_response(
            f"Skill '{name}' is now "
            f"{'enabled' if enabled else 'disabled'} "
            f"in workspace {workspace.name}.\n"
            "Note: the running agent may need a reload/new turn to pick this up.",
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("skill_set_enabled failed: %s", exc)
        return _make_response(f"skill_set_enabled failed: {exc}", ok=False)


@tool_descriptor(
    async_execution=True,
    tool_type="internal",
    target_param="query",
    policy_name="OrgSkillList",
    default_policy="allow",
    policy_reason="List organization market skills",
    ui_description="List organization skill market entries",
    ui_icon="🗂️",
)
async def org_skill_list(
    query: str = "",
    mine: bool = False,
    category: str = "",
    limit: int = 20,
) -> ToolChunk:
    """List skills on the organization market (optionally filter by keyword).

    Args:
        query: Optional substring filter on name / display_name / description.
        mine: If true, only skills owned by the current Hub user.
        category: Optional category filter.
        limit: Max rows (1–50, default 20).
    """
    db = _hub_db()
    if db is None:
        return _make_response(
            "Organization skill market is not configured.",
            ok=False,
        )
    user_id = _hub_user_id()
    try:
        from ...hub.org_skills.service import OrgSkillsService

        service = OrgSkillsService(db)
        items = service.list_visible(
            is_hub_member=True,
            mine_only=bool(mine),
            user_id=user_id,
            category=(category or "").strip().lower() or None,
        )
        needle = (query or "").strip().lower()
        if needle:
            items = [
                it
                for it in items
                if needle in str(it.get("name") or "").lower()
                or needle in str(it.get("display_name") or "").lower()
                or needle in str(it.get("description") or "").lower()
            ]
        capped = max(1, min(int(limit or 20), 50))
        items = items[:capped]
        if not items:
            return _make_response("No organization skills matched.")
        lines = [f"Organization skills ({len(items)}):", ""]
        for it in items:
            mark = []
            if it.get("installed"):
                mark.append("installed")
            if it.get("pinned"):
                mark.append("pinned")
            if it.get("update_available"):
                mark.append("update")
            if it.get("featured"):
                mark.append("featured")
            suffix = f" [{', '.join(mark)}]" if mark else ""
            lines.append(
                f"- {it.get('name')} v{it.get('version_text')}"
                f" · {it.get('display_name') or ''}"
                f" · id={it.get('skill_id')}{suffix}",
            )
        return _make_response("\n".join(lines))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("org_skill_list failed: %s", exc)
        return _make_response(f"org_skill_list failed: {exc}", ok=False)
