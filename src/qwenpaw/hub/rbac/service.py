# -*- coding: utf-8 -*-
"""Entitlement resolution and quota checks for BeeAgent Hub RBAC."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..runtime_token_usage import (
    iter_day_totals,
    personal_working_dir,
    sum_tokens_for_day,
)
from .catalog import (
    OFFICIAL_SKILLS,
    OFFICIAL_TOOLS,
    PERM_CHAT_USE,
    PERM_QUOTA_BYPASS,
    matches_permission,
    skill_permission,
    tool_permission,
)
from . import store


class RbacService:
    """Resolve permissions/quotas against Hub control.db."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            check_same_thread=False,
            timeout=60.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            store.ensure_rbac_schema(connection)
            connection.commit()

    def entitlements(
        self,
        user_id: str,
        *,
        is_hub_admin: bool,
        ensure_default_role: bool = True,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            store.ensure_rbac_schema(connection)
            if ensure_default_role and not is_hub_admin:
                store.ensure_default_member_role(connection, user_id)
            role_ids = store.get_user_role_ids(connection, user_id)
            permissions: set[str] = set()
            if is_hub_admin:
                permissions.update(
                    {
                        PERM_CHAT_USE,
                        "skill:use:*",
                        "tool:use:*",
                        "rbac:manage",
                        PERM_QUOTA_BYPASS,
                        "*",
                    },
                )
            for role_id in role_ids:
                row = connection.execute(
                    "SELECT permissions_json FROM hub_rbac_roles "
                    "WHERE role_id = ?",
                    (role_id,),
                ).fetchone()
                if row is None:
                    continue
                permissions.update(json.loads(row["permissions_json"]))
            overrides = store.get_user_overrides(connection, user_id)
            denied: set[str] = set()
            for item in overrides:
                if item["effect"] == "allow":
                    permissions.add(item["permission"])
                elif item["effect"] == "deny":
                    denied.add(item["permission"])
                    permissions.discard(item["permission"])
            allowed_skills = self._allowed_skills(
                permissions,
                is_hub_admin,
                denied=denied,
            )
            allowed_tools = self._allowed_tools(
                permissions,
                is_hub_admin,
                denied=denied,
            )
            quota = self._effective_quota(connection, user_id, permissions)
            today = self._today(quota.get("timezone") or "Asia/Shanghai")
            # BeeAgent personal runtimes usually call providers directly, so
            # Hub model-gateway token ledgers stay empty. Mirror today's
            # absolute totals from the runtime token_usage.json into RBAC.
            self._sync_runtime_tokens(connection, user_id, today)
            usage = store.get_usage(connection, user_id, today)
            connection.commit()
            return {
                "user_id": user_id,
                "is_hub_admin": is_hub_admin,
                "roles": role_ids,
                "permissions": sorted(permissions),
                "allowed_skills": allowed_skills,
                "allowed_tools": allowed_tools,
                "quota": quota,
                "usage_today": usage,
                "usage_date": today,
            }

    def _allowed_skills(
        self,
        permissions: set[str],
        is_hub_admin: bool,
        *,
        denied: set[str] | None = None,
    ) -> list[str]:
        denied = denied or set()
        if is_hub_admin or "*" in permissions:
            base = list(OFFICIAL_SKILLS)
        else:
            base = []
            for name in OFFICIAL_SKILLS:
                needed = skill_permission(name)
                if matches_permission(permissions, needed):
                    base.append(name)
        out = []
        for name in base:
            needed = skill_permission(name)
            if needed in denied or "skill:use:*" in denied or "skill:use" in denied:
                continue
            out.append(name)
        return out

    def _allowed_tools(
        self,
        permissions: set[str],
        is_hub_admin: bool,
        *,
        denied: set[str] | None = None,
    ) -> list[str]:
        denied = denied or set()
        if is_hub_admin or "*" in permissions:
            base = list(OFFICIAL_TOOLS)
        else:
            base = []
            for name in OFFICIAL_TOOLS:
                needed = tool_permission(name)
                if matches_permission(permissions, needed):
                    base.append(name)
        out = []
        for name in base:
            needed = tool_permission(name)
            if needed in denied or "tool:use:*" in denied or "tool:use" in denied:
                continue
            out.append(name)
        return out

    def _effective_quota(
        self,
        connection: sqlite3.Connection,
        user_id: str,
        permissions: set[str],
    ) -> dict[str, Any]:
        org = store.get_org_defaults(connection)
        row = store.get_user_quota_row(connection, user_id)
        inherit = True if row is None else bool(row["inherit_org_defaults"])
        daily_chat = org.get("daily_chat_limit", -1)
        daily_token = org.get("daily_token_limit", -1)
        if row is not None and not inherit:
            if row["daily_chat_limit"] is not None:
                daily_chat = row["daily_chat_limit"]
            if row["daily_token_limit"] is not None:
                daily_token = row["daily_token_limit"]
        return {
            "daily_chat_limit": daily_chat,
            "daily_token_limit": daily_token,
            "timezone": org.get("timezone") or "Asia/Shanghai",
            "inherit_org_defaults": inherit,
            "bypass": matches_permission(permissions, PERM_QUOTA_BYPASS)
            or "*" in permissions,
        }

    @staticmethod
    def _today(tz_name: str) -> str:
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("Asia/Shanghai")
        return datetime.now(tz).strftime("%Y-%m-%d")

    def can_chat(self, entitlements: dict[str, Any]) -> tuple[bool, str]:
        perms = set(entitlements.get("permissions") or [])
        if not matches_permission(perms, PERM_CHAT_USE) and "*" not in perms:
            return False, "缺少 chat:use 权限"
        quota = entitlements.get("quota") or {}
        if quota.get("bypass"):
            return True, ""
        limit = int(quota.get("daily_chat_limit", -1))
        if limit < 0:
            return True, ""
        used = int((entitlements.get("usage_today") or {}).get("chat_count") or 0)
        if used >= limit:
            return False, f"已达每日对话上限 ({limit})"
        return True, ""

    def can_use_skill(
        self,
        entitlements: dict[str, Any],
        skill_name: str,
    ) -> tuple[bool, str]:
        allowed = set(entitlements.get("allowed_skills") or [])
        if skill_name in allowed:
            return True, ""
        return False, f"无权限使用 skill: {skill_name}"

    def record_chat(self, user_id: str, *, token_delta: int = 0) -> dict[str, int]:
        with self._connect() as connection:
            store.ensure_rbac_schema(connection)
            org = store.get_org_defaults(connection)
            today = self._today(org.get("timezone") or "Asia/Shanghai")
            usage = store.add_usage(
                connection,
                user_id,
                today,
                chat_delta=1,
                token_delta=max(0, int(token_delta)),
            )
            self._sync_runtime_tokens(connection, user_id, today)
            usage = store.get_usage(connection, user_id, today)
            connection.commit()
            return usage

    def record_tokens(self, user_id: str, token_delta: int) -> dict[str, int]:
        with self._connect() as connection:
            store.ensure_rbac_schema(connection)
            org = store.get_org_defaults(connection)
            today = self._today(org.get("timezone") or "Asia/Shanghai")
            usage = store.add_usage(
                connection,
                user_id,
                today,
                chat_delta=0,
                token_delta=max(0, int(token_delta)),
            )
            connection.commit()
            return usage

    def _sync_runtime_tokens(
        self,
        connection: sqlite3.Connection,
        user_id: str,
        usage_date: str,
    ) -> None:
        working = personal_working_dir(connection, user_id)
        if working is None:
            return
        usage_path = working / "token_usage.json"
        # Mirror every day present in the runtime file, plus today (may be 0).
        day_totals = iter_day_totals(usage_path)
        if usage_date not in day_totals:
            today_total = sum_tokens_for_day(usage_path, usage_date)
            if today_total is not None:
                day_totals[usage_date] = today_total
        if not day_totals:
            return
        for day, total in day_totals.items():
            store.set_token_count(connection, user_id, day, total)

    def sync_runtime_token_usage(self, user_id: str) -> dict[str, int]:
        """Refresh one user's RBAC token_count from runtime usage file."""
        with self._connect() as connection:
            store.ensure_rbac_schema(connection)
            org = store.get_org_defaults(connection)
            today = self._today(org.get("timezone") or "Asia/Shanghai")
            self._sync_runtime_tokens(connection, user_id, today)
            usage = store.get_usage(connection, user_id, today)
            connection.commit()
            return usage

    def admit_chat(
        self,
        user_id: str,
        *,
        is_hub_admin: bool,
        consume: bool = True,
    ) -> dict[str, Any]:
        """Authorize one chat turn; optionally consume daily chat quota."""
        ent = self.entitlements(user_id, is_hub_admin=is_hub_admin)
        ok, reason = self.can_chat(ent)
        if not ok:
            raise PermissionError(reason or "chat_denied")
        if consume:
            # Always count chats for admin stats (even when unlimited / bypass).
            # Token totals are mirrored from the runtime usage file.
            self.record_chat(user_id)
            ent = self.entitlements(
                user_id,
                is_hub_admin=is_hub_admin,
                ensure_default_role=False,
            )
        return ent

    def admit_tokens(
        self,
        user_id: str,
        *,
        is_hub_admin: bool,
        reserved_tokens: int,
    ) -> dict[str, Any]:
        """Reject when daily token remaining cannot cover reservation."""
        ent = self.entitlements(user_id, is_hub_admin=is_hub_admin)
        quota = ent.get("quota") or {}
        if quota.get("bypass"):
            return ent
        limit = int(quota.get("daily_token_limit", -1))
        if limit < 0:
            return ent
        used = int((ent.get("usage_today") or {}).get("token_count") or 0)
        if used + max(0, int(reserved_tokens)) > limit:
            raise PermissionError(
                f"已达每日 Token 上限 ({limit})，今日已用 {used}",
            )
        return ent

    def lookup_is_hub_admin(self, user_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT role FROM hub_users WHERE user_id = ? "
                "AND disabled = 0 AND deleted_at IS NULL",
                (user_id,),
            ).fetchone()
            return bool(row and str(row["role"]) == "admin")

    def apply_skill_acl_to_workspace(
        self,
        workspace_skill_json: Path,
        allowed_skills: list[str],
    ) -> int:
        """Enable official skills in allow-list; disable the rest. Return changes."""
        if not workspace_skill_json.exists():
            return 0
        data = json.loads(workspace_skill_json.read_text(encoding="utf-8"))
        skills = data.setdefault("skills", {})
        allowed = set(allowed_skills)
        changed = 0
        for name in OFFICIAL_SKILLS:
            entry = skills.get(name)
            if not isinstance(entry, dict):
                continue
            want = name in allowed
            if bool(entry.get("enabled")) != want:
                entry["enabled"] = want
                changed += 1
        if changed:
            workspace_skill_json.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return changed
