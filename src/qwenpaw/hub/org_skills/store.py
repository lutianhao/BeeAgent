# -*- coding: utf-8 -*-
"""SQLite persistence for BeeAgent organization skill market."""

from __future__ import annotations

import json
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


_SUMMARY_COLS = (
    "skill_id, name, display_name, description, emoji, visibility, "
    "version_text, owner_user_id, owner_username, created_at, updated_at, "
    "deleted_at, "
    "COALESCE(has_bundle, 0) AS has_bundle, "
    "COALESCE(changelog, '') AS changelog, "
    "COALESCE(category, 'other') AS category, "
    "COALESCE(featured, 0) AS featured, "
    "COALESCE(status, 'active') AS status, "
    "COALESCE(compatibility, '') AS compatibility, "
    "COALESCE(allowed_tools, '') AS allowed_tools"
)


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
    if "changelog" not in columns:
        connection.execute(
            "ALTER TABLE hub_org_skills "
            "ADD COLUMN changelog TEXT NOT NULL DEFAULT ''",
        )
    if "category" not in columns:
        connection.execute(
            "ALTER TABLE hub_org_skills "
            "ADD COLUMN category TEXT NOT NULL DEFAULT 'other'",
        )
    if "featured" not in columns:
        connection.execute(
            "ALTER TABLE hub_org_skills "
            "ADD COLUMN featured INTEGER NOT NULL DEFAULT 0",
        )
    if "status" not in columns:
        connection.execute(
            "ALTER TABLE hub_org_skills "
            "ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
        )
    if "compatibility" not in columns:
        connection.execute(
            "ALTER TABLE hub_org_skills "
            "ADD COLUMN compatibility TEXT NOT NULL DEFAULT ''",
        )
    if "allowed_tools" not in columns:
        connection.execute(
            "ALTER TABLE hub_org_skills "
            "ADD COLUMN allowed_tools TEXT NOT NULL DEFAULT ''",
        )
    install_cols = {
        str(row[1])
        for row in connection.execute(
            "PRAGMA table_info(hub_org_skill_installs)",
        )
    }
    if "installed_version" not in install_cols:
        connection.execute(
            "ALTER TABLE hub_org_skill_installs "
            "ADD COLUMN installed_version TEXT NOT NULL DEFAULT ''",
        )
    if "pinned" not in install_cols:
        connection.execute(
            "ALTER TABLE hub_org_skill_installs "
            "ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0",
        )


def list_skills(
    connection: sqlite3.Connection,
    *,
    include_public: bool,
    include_org: bool,
    include_personal_for: str | None = None,
    owner_user_id: str | None = None,
    include_delisted: bool = False,
    include_deleted: bool = False,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """List catalog rows.

    Soft-deleted rows (``deleted_at`` set) are excluded unless
    ``include_deleted`` is true (recycle bin). Personal visibility rows are
    only included when ``include_personal_for`` matches their owner (or the
    caller uses ``owner_user_id`` / mine filter).
    """
    params: list[Any] = []
    if include_deleted:
        # Recycle bin: soft-deleted only; visibility filter skipped (owner scope
        # applied via owner_user_id when not manage).
        clauses = ["deleted_at IS NOT NULL"]
        if owner_user_id:
            clauses.append("owner_user_id = ?")
            params.append(owner_user_id)
    else:
        clauses = ["deleted_at IS NULL"]
        # Visibility: org/public for everyone; personal only for the viewer.
        vis_parts: list[str] = []
        if include_org:
            vis_parts.append("visibility = 'org'")
        if include_public:
            vis_parts.append("visibility = 'public'")
        if include_personal_for:
            vis_parts.append("(visibility = 'personal' AND owner_user_id = ?)")
            params.append(include_personal_for)
        if not vis_parts:
            return []
        clauses.append("(" + " OR ".join(vis_parts) + ")")
        if owner_user_id:
            clauses.append("owner_user_id = ?")
            params.append(owner_user_id)
        if not include_delisted:
            clauses.append("COALESCE(status, 'active') = 'active'")
        else:
            clauses.append(
                "COALESCE(status, 'active') IN ('active', 'delisted')",
            )
    if category:
        clauses.append("COALESCE(category, 'other') = ?")
        params.append(category)
    where = " AND ".join(clauses)
    rows = connection.execute(
        f"SELECT {_SUMMARY_COLS} FROM hub_org_skills WHERE {where} "
        "ORDER BY COALESCE(featured, 0) DESC, updated_at DESC",
        params,
    ).fetchall()
    return [_row_summary(row) for row in rows]


def get_skill(
    connection: sqlite3.Connection,
    skill_id: str,
    *,
    include_content: bool = False,
) -> dict[str, Any] | None:
    cols = _SUMMARY_COLS
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
        f"SELECT {_SUMMARY_COLS}, content_md "
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
    changelog: str = "",
    category: str = "other",
    compatibility: str = "",
    allowed_tools: str = "",
) -> dict[str, Any]:
    now = utc_now()
    connection.execute(
        "INSERT INTO hub_org_skills("
        "skill_id, name, display_name, description, emoji, visibility, "
        "content_md, version_text, owner_user_id, owner_username, "
        "created_at, updated_at, has_bundle, changelog, category, "
        "featured, status, compatibility, allowed_tools) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'active', "
        "?, ?)",
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
            (changelog or "").strip(),
            (category or "other").strip().lower() or "other",
            (compatibility or "").strip(),
            (allowed_tools or "").strip(),
        ),
    )
    return get_skill(connection, skill_id, include_content=False) or {}


def update_skill(
    connection: sqlite3.Connection,
    *,
    skill_id: str,
    display_name: str,
    description: str,
    emoji: str,
    visibility: str,
    content_md: str,
    version_text: str,
    has_bundle: bool = True,
    changelog: str = "",
    category: str | None = None,
    compatibility: str = "",
    allowed_tools: str = "",
) -> dict[str, Any]:
    now = utc_now()
    compat = (compatibility or "").strip()
    tools = (allowed_tools or "").strip()
    if category is None:
        connection.execute(
            "UPDATE hub_org_skills SET "
            "display_name = ?, description = ?, emoji = ?, visibility = ?, "
            "content_md = ?, version_text = ?, updated_at = ?, has_bundle = ?, "
            "changelog = ?, compatibility = ?, allowed_tools = ? "
            "WHERE skill_id = ? AND deleted_at IS NULL",
            (
                display_name,
                description,
                emoji,
                visibility,
                content_md,
                version_text,
                now,
                1 if has_bundle else 0,
                (changelog or "").strip(),
                compat,
                tools,
                skill_id,
            ),
        )
    else:
        connection.execute(
            "UPDATE hub_org_skills SET "
            "display_name = ?, description = ?, emoji = ?, visibility = ?, "
            "content_md = ?, version_text = ?, updated_at = ?, has_bundle = ?, "
            "changelog = ?, category = ?, compatibility = ?, allowed_tools = ? "
            "WHERE skill_id = ? AND deleted_at IS NULL",
            (
                display_name,
                description,
                emoji,
                visibility,
                content_md,
                version_text,
                now,
                1 if has_bundle else 0,
                (changelog or "").strip(),
                (category or "other").strip().lower() or "other",
                compat,
                tools,
                skill_id,
            ),
        )
    return get_skill(connection, skill_id, include_content=False) or {}


def update_skill_ops(
    connection: sqlite3.Connection,
    skill_id: str,
    *,
    category: str | None = None,
    featured: bool | None = None,
    status: str | None = None,
    visibility: str | None = None,
) -> dict[str, Any] | None:
    """Patch operational fields (category / featured / shelf / visibility)."""
    existing = get_skill(connection, skill_id)
    if existing is None:
        return None
    sets: list[str] = ["updated_at = ?"]
    params: list[Any] = [utc_now()]
    if category is not None:
        sets.append("category = ?")
        params.append((category or "other").strip().lower() or "other")
    if featured is not None:
        sets.append("featured = ?")
        params.append(1 if featured else 0)
    if status is not None:
        normalized = (status or "active").strip().lower()
        if normalized not in {"active", "delisted"}:
            raise ValueError("status 只能是 active 或 delisted")
        sets.append("status = ?")
        params.append(normalized)
        # Relisting clears a mistaken soft-delete marker if any.
        if normalized == "active":
            sets.append("deleted_at = NULL")
    if visibility is not None:
        vis = (visibility or "org").strip().lower()
        if vis not in {"org", "public", "personal"}:
            raise ValueError("visibility 只能是 personal、org 或 public")
        sets.append("visibility = ?")
        params.append(vis)
    params.append(skill_id)
    connection.execute(
        f"UPDATE hub_org_skills SET {', '.join(sets)} "
        "WHERE skill_id = ? AND deleted_at IS NULL",
        params,
    )
    return get_skill(connection, skill_id)


def count_installs(
    connection: sqlite3.Connection,
    skill_ids: list[str],
) -> dict[str, int]:
    if not skill_ids:
        return {}
    placeholders = ",".join("?" for _ in skill_ids)
    rows = connection.execute(
        "SELECT skill_id, COUNT(*) AS cnt FROM hub_org_skill_installs "
        f"WHERE skill_id IN ({placeholders}) GROUP BY skill_id",
        skill_ids,
    ).fetchall()
    return {str(r["skill_id"]): int(r["cnt"]) for r in rows}


def soft_delete_skill(
    connection: sqlite3.Connection,
    skill_id: str,
    *,
    actor_user_id: str,
    is_admin: bool,
    can_manage: bool = False,
) -> bool:
    row = connection.execute(
        "SELECT owner_user_id FROM hub_org_skills "
        "WHERE skill_id = ? AND deleted_at IS NULL",
        (skill_id,),
    ).fetchone()
    if row is None:
        return False
    if (
        not is_admin
        and not can_manage
        and str(row["owner_user_id"]) != actor_user_id
    ):
        raise PermissionError("只能删除自己发布的组织技能")
    now = utc_now()
    connection.execute(
        "UPDATE hub_org_skills SET deleted_at = ?, updated_at = ?, "
        "status = 'deleted' WHERE skill_id = ?",
        (now, now, skill_id),
    )
    return True


def restore_soft_deleted_skill(
    connection: sqlite3.Connection,
    skill_id: str,
    *,
    actor_user_id: str,
    is_admin: bool,
    can_manage: bool = False,
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT owner_user_id FROM hub_org_skills "
        "WHERE skill_id = ? AND deleted_at IS NOT NULL",
        (skill_id,),
    ).fetchone()
    if row is None:
        return None
    if (
        not is_admin
        and not can_manage
        and str(row["owner_user_id"]) != actor_user_id
    ):
        raise PermissionError("只能恢复自己删除的组织技能")
    now = utc_now()
    connection.execute(
        "UPDATE hub_org_skills SET deleted_at = NULL, updated_at = ?, "
        "status = 'active', visibility = CASE "
        "WHEN visibility = 'personal' THEN 'personal' ELSE visibility END "
        "WHERE skill_id = ?",
        (now, skill_id),
    )
    return get_skill(connection, skill_id)


def list_purgeable_skills(
    connection: sqlite3.Connection,
    *,
    older_than_iso: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        f"SELECT {_SUMMARY_COLS} FROM hub_org_skills "
        "WHERE deleted_at IS NOT NULL AND deleted_at < ? "
        "ORDER BY deleted_at ASC",
        (older_than_iso,),
    ).fetchall()
    return [_row_summary(row) for row in rows]


def hard_delete_skill(connection: sqlite3.Connection, skill_id: str) -> bool:
    cur = connection.execute(
        "DELETE FROM hub_org_skill_installs WHERE skill_id = ?",
        (skill_id,),
    )
    _ = cur
    cur2 = connection.execute(
        "DELETE FROM hub_org_skills WHERE skill_id = ?",
        (skill_id,),
    )
    return cur2.rowcount > 0


def record_install(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    skill_id: str,
    runtime_id: str,
    installed_version: str = "",
) -> None:
    """Upsert install row. Preserves ``pinned`` on conflict (upgrade keeps pin)."""
    connection.execute(
        "INSERT INTO hub_org_skill_installs("
        "user_id, skill_id, runtime_id, installed_at, installed_version, "
        "pinned) "
        "VALUES (?, ?, ?, ?, ?, 0) "
        "ON CONFLICT(user_id, skill_id) DO UPDATE SET "
        "runtime_id = excluded.runtime_id, "
        "installed_at = excluded.installed_at, "
        "installed_version = excluded.installed_version",
        (
            user_id,
            skill_id,
            runtime_id,
            utc_now(),
            installed_version or "",
        ),
    )


def list_installs_for_user(
    connection: sqlite3.Connection,
    user_id: str,
) -> dict[str, dict[str, Any]]:
    """Return ``{skill_id: {installed_version, pinned}}`` for the user."""
    rows = connection.execute(
        "SELECT skill_id, "
        "COALESCE(installed_version, '') AS installed_version, "
        "COALESCE(pinned, 0) AS pinned "
        "FROM hub_org_skill_installs WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    return {
        str(r["skill_id"]): {
            "installed_version": str(r["installed_version"] or ""),
            "pinned": bool(r["pinned"]),
        }
        for r in rows
    }


def get_install(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    skill_id: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT skill_id, "
        "COALESCE(installed_version, '') AS installed_version, "
        "COALESCE(pinned, 0) AS pinned "
        "FROM hub_org_skill_installs "
        "WHERE user_id = ? AND skill_id = ?",
        (user_id, skill_id),
    ).fetchone()
    if row is None:
        return None
    return {
        "skill_id": str(row["skill_id"]),
        "installed_version": str(row["installed_version"] or ""),
        "pinned": bool(row["pinned"]),
    }


def set_install_pinned(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    skill_id: str,
    pinned: bool,
) -> dict[str, Any] | None:
    """Toggle pin on an existing install. Returns None if not installed."""
    cur = connection.execute(
        "UPDATE hub_org_skill_installs SET pinned = ? "
        "WHERE user_id = ? AND skill_id = ?",
        (1 if pinned else 0, user_id, skill_id),
    )
    if cur.rowcount <= 0:
        return None
    return get_install(connection, user_id=user_id, skill_id=skill_id)


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
    changelog = str(row["changelog"] or "") if "changelog" in keys else ""
    category = (
        str(row["category"] or "other") if "category" in keys else "other"
    )
    featured = bool(row["featured"]) if "featured" in keys else False
    status = str(row["status"] or "active") if "status" in keys else "active"
    compatibility = (
        str(row["compatibility"] or "") if "compatibility" in keys else ""
    )
    allowed_tools_raw = (
        str(row["allowed_tools"] or "") if "allowed_tools" in keys else ""
    )
    allowed_tools: list[str] = []
    if allowed_tools_raw.strip():
        try:
            parsed = json.loads(allowed_tools_raw)
            if isinstance(parsed, list):
                allowed_tools = [
                    str(x).strip() for x in parsed if str(x).strip()
                ]
        except json.JSONDecodeError:
            allowed_tools = [
                part.strip()
                for part in allowed_tools_raw.split(",")
                if part.strip()
            ]
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
        "deleted_at": (
            str(row["deleted_at"])
            if "deleted_at" in keys and row["deleted_at"] is not None
            else None
        ),
        "has_bundle": has_bundle,
        "changelog": changelog,
        "category": category or "other",
        "featured": featured,
        "status": status or "active",
        "compatibility": compatibility,
        "allowed_tools": allowed_tools,
    }
