# -*- coding: utf-8 -*-
"""SQLite persistence for BeeAgent Hub RBAC."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .catalog import BUILTIN_ROLES, DEFAULT_ORG_QUOTA

RBAC_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS hub_rbac_roles (
    role_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_system INTEGER NOT NULL DEFAULT 0,
    permissions_json TEXT NOT NULL CHECK(json_valid(permissions_json)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hub_rbac_user_roles (
    user_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    assigned_by TEXT,
    PRIMARY KEY (user_id, role_id),
    FOREIGN KEY (role_id) REFERENCES hub_rbac_roles(role_id)
);

CREATE TABLE IF NOT EXISTS hub_rbac_user_overrides (
    user_id TEXT NOT NULL,
    permission TEXT NOT NULL,
    effect TEXT NOT NULL CHECK(effect IN ('allow', 'deny')),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, permission)
);

CREATE TABLE IF NOT EXISTS hub_rbac_user_quotas (
    user_id TEXT PRIMARY KEY,
    daily_chat_limit INTEGER,
    daily_token_limit INTEGER,
    inherit_org_defaults INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hub_rbac_usage_daily (
    user_id TEXT NOT NULL,
    usage_date TEXT NOT NULL,
    chat_count INTEGER NOT NULL DEFAULT 0,
    token_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, usage_date)
);

CREATE INDEX IF NOT EXISTS idx_rbac_user_roles_user
ON hub_rbac_user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_rbac_usage_date
ON hub_rbac_usage_daily(usage_date);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def ensure_rbac_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(RBAC_SCHEMA_SQL)
    now = utc_now()
    for role_id, meta in BUILTIN_ROLES.items():
        connection.execute(
            "INSERT OR IGNORE INTO hub_rbac_roles("
            "role_id, name, description, is_system, permissions_json, "
            "created_at, updated_at) VALUES (?, ?, ?, 1, ?, ?, ?)",
            (
                role_id,
                meta["name"],
                meta["description"],
                json.dumps(list(meta["permissions"]), ensure_ascii=False),
                now,
                now,
            ),
        )
    # Keep system role permissions in sync with catalog on upgrade
    for role_id, meta in BUILTIN_ROLES.items():
        connection.execute(
            "UPDATE hub_rbac_roles SET name = ?, description = ?, "
            "permissions_json = ?, updated_at = ? "
            "WHERE role_id = ? AND is_system = 1",
            (
                meta["name"],
                meta["description"],
                json.dumps(list(meta["permissions"]), ensure_ascii=False),
                now,
                role_id,
            ),
        )
    row = connection.execute(
        "SELECT value_json FROM hub_settings WHERE key = ?",
        ("beeagent_rbac_defaults",),
    ).fetchone()
    if row is None:
        connection.execute(
            "INSERT INTO hub_settings("
            "key, value_json, schema_version, revision, updated_at) "
            "VALUES (?, ?, 1, 1, ?)",
            (
                "beeagent_rbac_defaults",
                json.dumps(DEFAULT_ORG_QUOTA, ensure_ascii=False),
                now,
            ),
        )


def list_roles(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT role_id, name, description, is_system, permissions_json, "
        "created_at, updated_at FROM hub_rbac_roles ORDER BY role_id",
    ).fetchall()
    out = []
    for row in rows:
        out.append(
            {
                "role_id": row["role_id"],
                "name": row["name"],
                "description": row["description"],
                "is_system": bool(row["is_system"]),
                "permissions": json.loads(row["permissions_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
        )
    return out


def upsert_role(
    connection: sqlite3.Connection,
    *,
    role_id: str,
    name: str,
    description: str,
    permissions: list[str],
    is_system: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    connection.execute(
        "INSERT INTO hub_rbac_roles("
        "role_id, name, description, is_system, permissions_json, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(role_id) DO UPDATE SET "
        "name = excluded.name, "
        "description = excluded.description, "
        "permissions_json = excluded.permissions_json, "
        "updated_at = excluded.updated_at "
        "WHERE hub_rbac_roles.is_system = 0 OR excluded.is_system = 1",
        (
            role_id,
            name,
            description,
            1 if is_system else 0,
            json.dumps(list(permissions), ensure_ascii=False),
            now,
            now,
        ),
    )
    row = connection.execute(
        "SELECT role_id, name, description, is_system, permissions_json, "
        "created_at, updated_at FROM hub_rbac_roles WHERE role_id = ?",
        (role_id,),
    ).fetchone()
    return {
        "role_id": row["role_id"],
        "name": row["name"],
        "description": row["description"],
        "is_system": bool(row["is_system"]),
        "permissions": json.loads(row["permissions_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def delete_role(connection: sqlite3.Connection, role_id: str) -> bool:
    row = connection.execute(
        "SELECT is_system FROM hub_rbac_roles WHERE role_id = ?",
        (role_id,),
    ).fetchone()
    if row is None:
        return False
    if int(row["is_system"]) == 1:
        raise ValueError("Cannot delete system role")
    connection.execute(
        "DELETE FROM hub_rbac_user_roles WHERE role_id = ?",
        (role_id,),
    )
    connection.execute(
        "DELETE FROM hub_rbac_roles WHERE role_id = ?",
        (role_id,),
    )
    return True


def get_user_role_ids(
    connection: sqlite3.Connection,
    user_id: str,
) -> list[str]:
    rows = connection.execute(
        "SELECT role_id FROM hub_rbac_user_roles WHERE user_id = ? "
        "ORDER BY role_id",
        (user_id,),
    ).fetchall()
    return [str(r["role_id"]) for r in rows]


def set_user_roles(
    connection: sqlite3.Connection,
    user_id: str,
    role_ids: list[str],
    *,
    assigned_by: str | None,
) -> list[str]:
    now = utc_now()
    connection.execute(
        "DELETE FROM hub_rbac_user_roles WHERE user_id = ?",
        (user_id,),
    )
    for role_id in role_ids:
        exists = connection.execute(
            "SELECT 1 FROM hub_rbac_roles WHERE role_id = ?",
            (role_id,),
        ).fetchone()
        if exists is None:
            raise ValueError(f"Unknown role: {role_id}")
        connection.execute(
            "INSERT INTO hub_rbac_user_roles("
            "user_id, role_id, assigned_at, assigned_by) "
            "VALUES (?, ?, ?, ?)",
            (user_id, role_id, now, assigned_by),
        )
    return get_user_role_ids(connection, user_id)


def ensure_default_member_role(
    connection: sqlite3.Connection,
    user_id: str,
) -> None:
    """Assign bee.member once if the user has no RBAC roles yet."""
    existing = get_user_role_ids(connection, user_id)
    if existing:
        return
    set_user_roles(
        connection,
        user_id,
        ["bee.member"],
        assigned_by="system",
    )


def get_user_overrides(
    connection: sqlite3.Connection,
    user_id: str,
) -> list[dict[str, str]]:
    rows = connection.execute(
        "SELECT permission, effect FROM hub_rbac_user_overrides "
        "WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    return [
        {"permission": r["permission"], "effect": r["effect"]} for r in rows
    ]


def set_user_overrides(
    connection: sqlite3.Connection,
    user_id: str,
    overrides: list[dict[str, str]],
) -> list[dict[str, str]]:
    now = utc_now()
    connection.execute(
        "DELETE FROM hub_rbac_user_overrides WHERE user_id = ?",
        (user_id,),
    )
    for item in overrides:
        effect = item.get("effect") or "allow"
        if effect not in {"allow", "deny"}:
            raise ValueError("effect must be allow or deny")
        permission = str(item.get("permission") or "").strip()
        if not permission:
            continue
        connection.execute(
            "INSERT INTO hub_rbac_user_overrides("
            "user_id, permission, effect, updated_at) VALUES (?, ?, ?, ?)",
            (user_id, permission, effect, now),
        )
    return get_user_overrides(connection, user_id)


def get_org_defaults(connection: sqlite3.Connection) -> dict[str, Any]:
    row = connection.execute(
        "SELECT value_json FROM hub_settings WHERE key = ?",
        ("beeagent_rbac_defaults",),
    ).fetchone()
    if row is None:
        return dict(DEFAULT_ORG_QUOTA)
    data = json.loads(row["value_json"])
    merged = dict(DEFAULT_ORG_QUOTA)
    merged.update(data)
    return merged


def set_org_defaults(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
) -> dict[str, Any]:
    now = utc_now()
    current = get_org_defaults(connection)
    current.update(payload)
    connection.execute(
        "INSERT INTO hub_settings("
        "key, value_json, schema_version, revision, updated_at) "
        "VALUES (?, ?, 1, 1, ?) "
        "ON CONFLICT(key) DO UPDATE SET "
        "value_json = excluded.value_json, "
        "revision = hub_settings.revision + 1, "
        "updated_at = excluded.updated_at",
        (
            "beeagent_rbac_defaults",
            json.dumps(current, ensure_ascii=False),
            now,
        ),
    )
    return current


def get_user_quota_row(
    connection: sqlite3.Connection,
    user_id: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT user_id, daily_chat_limit, daily_token_limit, "
        "inherit_org_defaults, updated_at FROM hub_rbac_user_quotas "
        "WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "user_id": row["user_id"],
        "daily_chat_limit": row["daily_chat_limit"],
        "daily_token_limit": row["daily_token_limit"],
        "inherit_org_defaults": bool(row["inherit_org_defaults"]),
        "updated_at": row["updated_at"],
    }


def set_user_quota(
    connection: sqlite3.Connection,
    user_id: str,
    *,
    daily_chat_limit: int | None,
    daily_token_limit: int | None,
    inherit_org_defaults: bool,
) -> dict[str, Any]:
    now = utc_now()
    connection.execute(
        "INSERT INTO hub_rbac_user_quotas("
        "user_id, daily_chat_limit, daily_token_limit, "
        "inherit_org_defaults, updated_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET "
        "daily_chat_limit = excluded.daily_chat_limit, "
        "daily_token_limit = excluded.daily_token_limit, "
        "inherit_org_defaults = excluded.inherit_org_defaults, "
        "updated_at = excluded.updated_at",
        (
            user_id,
            daily_chat_limit,
            daily_token_limit,
            1 if inherit_org_defaults else 0,
            now,
        ),
    )
    row = get_user_quota_row(connection, user_id)
    assert row is not None
    return row


def get_usage(
    connection: sqlite3.Connection,
    user_id: str,
    usage_date: str,
) -> dict[str, int]:
    row = connection.execute(
        "SELECT chat_count, token_count FROM hub_rbac_usage_daily "
        "WHERE user_id = ? AND usage_date = ?",
        (user_id, usage_date),
    ).fetchone()
    if row is None:
        return {"chat_count": 0, "token_count": 0}
    return {
        "chat_count": int(row["chat_count"]),
        "token_count": int(row["token_count"]),
    }


def add_usage(
    connection: sqlite3.Connection,
    user_id: str,
    usage_date: str,
    *,
    chat_delta: int = 0,
    token_delta: int = 0,
) -> dict[str, int]:
    now = utc_now()
    connection.execute(
        "INSERT INTO hub_rbac_usage_daily("
        "user_id, usage_date, chat_count, token_count, updated_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id, usage_date) DO UPDATE SET "
        "chat_count = hub_rbac_usage_daily.chat_count + excluded.chat_count, "
        "token_count = hub_rbac_usage_daily.token_count + excluded.token_count, "
        "updated_at = excluded.updated_at",
        (user_id, usage_date, chat_delta, token_delta, now),
    )
    return get_usage(connection, user_id, usage_date)


def set_token_count(
    connection: sqlite3.Connection,
    user_id: str,
    usage_date: str,
    token_count: int,
) -> dict[str, int]:
    """Set absolute daily token_count (preserves chat_count)."""
    now = utc_now()
    tokens = max(0, int(token_count))
    connection.execute(
        "INSERT INTO hub_rbac_usage_daily("
        "user_id, usage_date, chat_count, token_count, updated_at) "
        "VALUES (?, ?, 0, ?, ?) "
        "ON CONFLICT(user_id, usage_date) DO UPDATE SET "
        "token_count = excluded.token_count, "
        "updated_at = excluded.updated_at",
        (user_id, usage_date, tokens, now),
    )
    return get_usage(connection, user_id, usage_date)
