# -*- coding: utf-8 -*-
"""Permission catalog for BeeAgent Hub RBAC extension."""

from __future__ import annotations

# Stable permission strings (resource:verb[:id])
PERM_CHAT_USE = "chat:use"
PERM_SKILL_USE = "skill:use"
PERM_SKILL_USE_ALL = "skill:use:*"
PERM_TOOL_USE = "tool:use"
PERM_TOOL_USE_ALL = "tool:use:*"
PERM_RBAC_MANAGE = "rbac:manage"
PERM_QUOTA_BYPASS = "quota:bypass"

OFFICIAL_SKILLS = (
    "koujing-xiezhuan",
    "wangping-huashu",
    "shensu-chegao",
    "yuqing-yanpan",
    "yuan-xiezhuan",
    "shiqian-pinggu",
    "paicha-fangan",
    "weike-wenan",
    "yanlian-jiaoben",
    "shuju-chuli",
    "yuqing-baogao",
)

# Controllable builtin tools for BeeAgent general agent.
OFFICIAL_TOOLS = (
    "web_search",
    "web_fetch",
)

BUILTIN_ROLES: dict[str, dict] = {
    "bee.member": {
        "name": "成员",
        "description": "可对话，可使用全部官方 Skills 与联网工具",
        "permissions": [PERM_CHAT_USE, PERM_SKILL_USE_ALL, PERM_TOOL_USE_ALL],
        "system": True,
    },
    "bee.restricted": {
        "name": "受限成员",
        "description": "仅通用对话，不可用专项 Skills / 联网工具",
        "permissions": [PERM_CHAT_USE],
        "system": True,
    },
    "bee.operator": {
        "name": "业务管理员",
        "description": "成员权限 + 管理 RBAC/配额（非 Hub 超管）",
        "permissions": [
            PERM_CHAT_USE,
            PERM_SKILL_USE_ALL,
            PERM_TOOL_USE_ALL,
            PERM_RBAC_MANAGE,
            PERM_QUOTA_BYPASS,
        ],
        "system": True,
    },
}

DEFAULT_ORG_QUOTA = {
    "daily_chat_limit": -1,
    "daily_token_limit": -1,
    "timezone": "Asia/Shanghai",
}


def skill_permission(skill_name: str) -> str:
    return f"skill:use:{skill_name}"


def tool_permission(tool_name: str) -> str:
    return f"tool:use:{tool_name}"


def matches_permission(granted: set[str], needed: str) -> bool:
    """Return True if needed is covered by granted set (supports *)."""
    if needed in granted or "*" in granted:
        return True
    # skill:use:* covers skill:use and skill:use:<name>
    if needed == PERM_SKILL_USE or needed.startswith("skill:use:"):
        if PERM_SKILL_USE_ALL in granted or PERM_SKILL_USE in granted:
            return True
    # tool:use:* covers tool:use and tool:use:<name>
    if needed == PERM_TOOL_USE or needed.startswith("tool:use:"):
        if PERM_TOOL_USE_ALL in granted or PERM_TOOL_USE in granted:
            return True
    # prefix wildcards: "skill:use:*" already handled; future "admin:*"
    parts = needed.split(":")
    if len(parts) >= 2:
        wildcard = f"{parts[0]}:*"
        if wildcard in granted:
            return True
    return False
