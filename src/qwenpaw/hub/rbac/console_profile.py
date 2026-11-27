# -*- coding: utf-8 -*-
"""Console navigation / feature profile derived from Hub entitlements."""

from __future__ import annotations

from typing import Any, Mapping

from .catalog import (
    PERM_ORG_SKILL_MANAGE,
    PERM_ORG_SKILL_PUBLISH,
    matches_permission,
)

# Menu ids from console builtinMenu.ts — members only see the product surface.
_MEMBER_NAV_ALLOW: frozenset[str] = frozenset(
    {
        "core.inbox",
        "core.marketplace",
        "core.knowledge-base",
        "core.workspace-group",
        "core.files",
        "core.settings-group",
        "core.models",
        "core.token-usage",
    },
)

_OPERATOR_EXTRA: frozenset[str] = frozenset(
    {
        "core.agents",
        "core.skill-pool",
        "core.security",
    },
)


def build_console_profile(
    entitlements: Mapping[str, Any],
    *,
    username: str = "",
) -> dict[str, Any]:
    """Attach nav + feature flags for Console rendering (not a gate for writes)."""
    perms = set(entitlements.get("permissions") or [])
    is_admin = bool(entitlements.get("is_hub_admin"))
    can_publish = is_admin or matches_permission(perms, PERM_ORG_SKILL_PUBLISH)
    can_manage = is_admin or matches_permission(perms, PERM_ORG_SKILL_MANAGE)
    can_rbac = is_admin or "*" in perms or "rbac:manage" in perms
    can_kb_write = (
        is_admin or "org_kb:write" in perms or "org_kb:manage" in perms
    )
    can_kb_manage = is_admin or "org_kb:manage" in perms or "*" in perms

    if is_admin or can_rbac:
        nav_mode = "admin"
        nav_show: list[str] | None = None  # None = show all builtin items
        nav_hide: list[str] = []
    elif can_manage:
        nav_mode = "operator"
        nav_show = sorted(_MEMBER_NAV_ALLOW | _OPERATOR_EXTRA)
        nav_hide = []
    else:
        nav_mode = "member"
        nav_show = sorted(_MEMBER_NAV_ALLOW)
        nav_hide = []

    features = {
        "org_skill_publish": can_publish,
        "org_skill_manage": can_manage,
        "org_kb_write": can_kb_write,
        "org_kb_manage": can_kb_manage,
        "hub_governance": can_rbac or is_admin,
        "advanced_workspace": is_admin or can_manage,
    }

    return {
        **dict(entitlements),
        "username": username or entitlements.get("username") or "",
        "nav": {
            "mode": nav_mode,
            "show": nav_show,
            "hide": nav_hide,
            "advanced_collapsed": nav_mode == "member",
        },
        "features": features,
    }
