# -*- coding: utf-8 -*-
"""SQLite persistence for BeeAgent organization skill market."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS hub_org_skills (
    skill_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    emoji TEXT NOT NULL DEFAULT '🛠️',
    visibility TEXT NOT NULL DEFAULT 'org',
    content_md TEXT NOT NULL,
    version_text TEXT NOT NULL DEFAULT '1.0',
    owner_user_id TEXT NOT NULL,
    owner_username TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    has_bundle INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_hub_org_skills_visibility
    ON hub_org_skills(visibility, deleted_at);

CREATE TABLE IF NOT EXISTS hub_org_skill_installs (
    user_id TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    runtime_id TEXT NOT NULL DEFAULT '',
    installed_at TEXT NOT NULL,
    PRIMARY KEY (user_id, skill_id)
);
"""


def ensure_org_skills_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(_SCHEMA_SQL)
    columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(hub_org_skills)")
    }
    if "has_bundle" not in columns:
        connection.execute(
            "ALTER TABLE hub_org_skills "
            "ADD COLUMN has_bundle INTEGER NOT NULL DEFAULT 0",
        )


def list_skills(
    connection: sqlite3.Connection,
    *,
    include_public: bool,
    include_org: bool,
    owner_user_id: str | None = None,
) -> list[dict[str, Any]]:
    clauses = ["deleted_at IS NULL"]
    params: list[Any] = []
    visibility: list[str] = []
    if include_org:
        visibility.append("org")
    if include_public:
        visibility.append("public")
    if not visibility:
        return []
    placeholders = ",".join("?" for _ in visibility)
    clauses.append(f"visibility IN ({placeholders})")
    params.extend(visibility)
    if owner_user_id:
        clauses.append("owner_user_id = ?")
        params.append(owner_user_id)
    where = " AND ".join(clauses)
    rows = connection.execute(
        "SELECT skill_id, name, display_name, description, emoji, visibility, "
        "version_text, owner_user_id, owner_username, created_at, updated_at, "
        "COALESCE(has_bundle, 0) AS has_bundle "
        f"FROM hub_org_skills WHERE {where} "
        "ORDER BY updated_at DESC",
        params,
    ).fetchall()
    return [_row_summary(row) for row in rows]


def get_skill(
    connection: sqlite3.Connection,
    skill_id: str,
    *,
    include_content: bool = False,
) -> dict[str, Any] | None:
    cols = (
        "skill_id, name, display_name, description, emoji, visibility, "
        "version_text, owner_user_id, owner_username, created_at, updated_at, "
        "COALESCE(has_bundle, 0) AS has_bundle"
    )
    if include_content:
        cols += ", content_md"
    row = connection.execute(
        f"SELECT {cols} FROM hub_org_skills "
        "WHERE skill_id = ? AND deleted_at IS NULL",
        (skill_id,),
    ).fetchone()
    if row is None:
        return None
    data = _row_summary(row)
    if include_content:
        data["content_md"] = str(row["content_md"])
    return data


def get_skill_by_name(
    connection: sqlite3.Connection,
    name: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT skill_id, name, display_name, description, emoji, visibility, "
        "version_text, owner_user_id, owner_username, created_at, updated_at, "
        "COALESCE(has_bundle, 0) AS has_bundle, content_md "
        "FROM hub_org_skills "
        "WHERE name = ? AND deleted_at IS NULL",
        (name,),
    ).fetchone()
    if row is None:
        return None
    data = _row_summary(row)
    data["content_md"] = str(row["content_md"])
    return data


def create_skill(
    connection: sqlite3.Connection,
    *,
    skill_id: str,
    name: str,
    display_name: str,
    description: str,
    emoji: str,
    visibility: str,
    content_md: str,
    version_text: str,
    owner_user_id: str,
    owner_username: str,
    has_bundle: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    connection.execute(
        "INSERT INTO hub_org_skills("
        "skill_id, name, display_name, description, emoji, visibility, "
        "content_md, version_text, owner_user_id, owner_username, "
        "created_at, updated_at, has_bundle) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            skill_id,
            name,
            display_name,
            description,
            emoji,
            visibility,
            content_md,
            version_text,
            owner_user_id,
            owner_username,
            now,
            now,
            1 if has_bundle else 0,
        ),
    )
    return get_skill(connection, skill_id, include_content=False) or {}


def soft_delete_skill(
    connection: sqlite3.Connection,
    skill_id: str,
    *,
    actor_user_id: str,
    is_admin: bool,
) -> bool:
    row = connection.execute(
        "SELECT owner_user_id FROM hub_org_skills "
        "WHERE skill_id = ? AND deleted_at IS NULL",
        (skill_id,),
    ).fetchone()
    if row is None:
        return False
    if not is_admin and str(row["owner_user_id"]) != actor_user_id:
        raise PermissionError("只能删除自己发布的组织技能")
    connection.execute(
        "UPDATE hub_org_skills SET deleted_at = ?, updated_at = ? "
        "WHERE skill_id = ?",
        (utc_now(), utc_now(), skill_id),
    )
    return True


def record_install(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    skill_id: str,
    runtime_id: str,
) -> None:
    connection.execute(
        "INSERT INTO hub_org_skill_installs("
        "user_id, skill_id, runtime_id, installed_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, skill_id) DO UPDATE SET "
        "runtime_id = excluded.runtime_id, "
        "installed_at = excluded.installed_at",
        (user_id, skill_id, runtime_id, utc_now()),
    )


def list_installs_for_user(
    connection: sqlite3.Connection,
    user_id: str,
) -> list[str]:
    rows = connection.execute(
        "SELECT skill_id FROM hub_org_skill_installs WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    return [str(r["skill_id"]) for r in rows]


def remove_install(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    skill_id: str,
) -> bool:
    cur = connection.execute(
        "DELETE FROM hub_org_skill_installs "
        "WHERE user_id = ? AND skill_id = ?",
        (user_id, skill_id),
    )
    return cur.rowcount > 0


def _row_summary(row: sqlite3.Row) -> dict[str, Any]:
    keys = set(row.keys())
    has_bundle = bool(row["has_bundle"]) if "has_bundle" in keys else False
    return {
        "skill_id": str(row["skill_id"]),
        "name": str(row["name"]),
        "display_name": str(row["display_name"]),
        "description": str(row["description"] or ""),
        "emoji": str(row["emoji"] or "🛠️"),
        "visibility": str(row["visibility"]),
        "version_text": str(row["version_text"] or "1.0"),
        "owner_user_id": str(row["owner_user_id"]),
        "owner_username": str(row["owner_username"] or ""),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "has_bundle": has_bundle,
    }
