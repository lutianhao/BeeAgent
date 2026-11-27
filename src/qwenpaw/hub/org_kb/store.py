# -*- coding: utf-8 -*-
"""SQLite persistence for BeeAgent organization knowledge bases."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS hub_org_kbs (
    kb_id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    kb_type TEXT NOT NULL DEFAULT 'koujing',
    description TEXT NOT NULL DEFAULT '',
    visibility TEXT NOT NULL DEFAULT 'org',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_hub_org_kbs_type
    ON hub_org_kbs(kb_type, deleted_at);

CREATE TABLE IF NOT EXISTS hub_org_kb_docs (
    doc_id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL,
    title TEXT NOT NULL,
    filename TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL DEFAULT 'text/plain',
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT NOT NULL DEFAULT '',
    uploaded_by TEXT NOT NULL DEFAULT '',
    rel_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    FOREIGN KEY (kb_id) REFERENCES hub_org_kbs(kb_id)
);

CREATE INDEX IF NOT EXISTS idx_hub_org_kb_docs_kb
    ON hub_org_kb_docs(kb_id, deleted_at);

CREATE TABLE IF NOT EXISTS hub_org_kb_chunks (
    chunk_id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES hub_org_kb_docs(doc_id)
);

CREATE INDEX IF NOT EXISTS idx_hub_org_kb_chunks_doc
    ON hub_org_kb_chunks(doc_id);

CREATE VIRTUAL TABLE IF NOT EXISTS hub_org_kb_fts USING fts5(
    chunk_id UNINDEXED,
    kb_id UNINDEXED,
    doc_id UNINDEXED,
    title,
    body,
    tokenize = 'unicode61'
);

CREATE TABLE IF NOT EXISTS hub_skill_kb_bindings (
    skill_name TEXT NOT NULL,
    kb_slug TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (skill_name, kb_slug)
);

CREATE INDEX IF NOT EXISTS idx_hub_skill_kb_bindings_slug
    ON hub_skill_kb_bindings(kb_slug);

CREATE TABLE IF NOT EXISTS hub_org_kb_customer_grants (
    user_id TEXT NOT NULL,
    customer_key TEXT NOT NULL,
    granted_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, customer_key)
);

CREATE INDEX IF NOT EXISTS idx_hub_org_kb_customer_grants_key
    ON hub_org_kb_customer_grants(customer_key);

CREATE TABLE IF NOT EXISTS hub_org_kb_feedback (
    feedback_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL DEFAULT '',
    doc_id TEXT NOT NULL DEFAULT '',
    kb_id TEXT NOT NULL DEFAULT '',
    query TEXT NOT NULL DEFAULT '',
    useful INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hub_org_kb_feedback_chunk
    ON hub_org_kb_feedback(chunk_id, created_at);

CREATE INDEX IF NOT EXISTS idx_hub_org_kb_feedback_kb
    ON hub_org_kb_feedback(kb_id, useful);
"""

# Official BeeAgent skills → default org KB slugs (seeded once).
DEFAULT_SKILL_KB_BINDINGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("koujing-xiezhuan", ("koujing",)),
    ("yuan-xiezhuan", ("koujing",)),
    ("wangping-huashu", ("koujing",)),
    ("shensu-chegao", ("case", "koujing")),
    ("yuqing-yanpan", ("case",)),
    ("paicha-fangan", ("case",)),
    ("shiqian-pinggu", ("case",)),
    ("yuqing-baogao", ("template", "case")),
    ("weike-wenan", ("template", "koujing")),
    ("yanlian-jiaoben", ("template",)),
    ("shuju-chuli", ("koujing", "case")),
)


def ensure_org_kb_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(_SCHEMA_SQL)
    _ensure_doc_extra_columns(connection)
    seed_default_skill_kb_bindings(connection)


def _ensure_doc_extra_columns(connection: sqlite3.Connection) -> None:
    """Migrate older DBs that lack customer_key / effective window columns."""
    cols = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(hub_org_kb_docs)").fetchall()
    }
    if "customer_key" not in cols:
        connection.execute(
            "ALTER TABLE hub_org_kb_docs "
            "ADD COLUMN customer_key TEXT NOT NULL DEFAULT ''",
        )
    if "effective_from" not in cols:
        connection.execute(
            "ALTER TABLE hub_org_kb_docs "
            "ADD COLUMN effective_from TEXT NOT NULL DEFAULT ''",
        )
    if "effective_until" not in cols:
        connection.execute(
            "ALTER TABLE hub_org_kb_docs "
            "ADD COLUMN effective_until TEXT NOT NULL DEFAULT ''",
        )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_hub_org_kb_docs_customer "
        "ON hub_org_kb_docs(customer_key)",
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_hub_org_kb_docs_effective "
        "ON hub_org_kb_docs(effective_from, effective_until)",
    )


def seed_default_skill_kb_bindings(connection: sqlite3.Connection) -> int:
    """Insert official skill↔KB defaults when the skill has no rows yet."""
    inserted = 0
    for skill_name, slugs in DEFAULT_SKILL_KB_BINDINGS:
        existing = connection.execute(
            "SELECT 1 FROM hub_skill_kb_bindings WHERE skill_name = ? LIMIT 1",
            (skill_name,),
        ).fetchone()
        if existing is not None:
            continue
        for index, slug in enumerate(slugs):
            connection.execute(
                "INSERT OR IGNORE INTO hub_skill_kb_bindings("
                "skill_name, kb_slug, priority) VALUES (?, ?, ?)",
                (skill_name, slug, index),
            )
            inserted += 1
    return inserted


def list_kbs(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT kb_id, slug, name, kb_type, description, visibility, "
        "created_by, created_at, updated_at "
        "FROM hub_org_kbs WHERE deleted_at IS NULL "
        "ORDER BY updated_at DESC",
    ).fetchall()
    return [_kb_row(row) for row in rows]


def get_kb(
    connection: sqlite3.Connection,
    kb_id: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT kb_id, slug, name, kb_type, description, visibility, "
        "created_by, created_at, updated_at "
        "FROM hub_org_kbs WHERE kb_id = ? AND deleted_at IS NULL",
        (kb_id,),
    ).fetchone()
    return _kb_row(row) if row else None


def get_kb_by_slug(
    connection: sqlite3.Connection,
    slug: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT kb_id, slug, name, kb_type, description, visibility, "
        "created_by, created_at, updated_at "
        "FROM hub_org_kbs WHERE slug = ? AND deleted_at IS NULL",
        (slug,),
    ).fetchone()
    return _kb_row(row) if row else None


def create_kb(
    connection: sqlite3.Connection,
    *,
    kb_id: str,
    slug: str,
    name: str,
    kb_type: str,
    description: str,
    visibility: str,
    created_by: str,
) -> dict[str, Any]:
    now = utc_now()
    connection.execute(
        "INSERT INTO hub_org_kbs("
        "kb_id, slug, name, kb_type, description, visibility, "
        "created_by, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            kb_id,
            slug,
            name,
            kb_type,
            description,
            visibility,
            created_by,
            now,
            now,
        ),
    )
    return get_kb(connection, kb_id) or {}


def soft_delete_kb(connection: sqlite3.Connection, kb_id: str) -> bool:
    cur = connection.execute(
        "UPDATE hub_org_kbs SET deleted_at = ?, updated_at = ? "
        "WHERE kb_id = ? AND deleted_at IS NULL",
        (utc_now(), utc_now(), kb_id),
    )
    return cur.rowcount > 0


_DOC_SELECT = (
    "doc_id, kb_id, title, filename, content_type, status, error, "
    "uploaded_by, rel_path, customer_key, effective_from, effective_until, "
    "created_at, updated_at"
)


def list_docs(
    connection: sqlite3.Connection,
    kb_id: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        f"SELECT {_DOC_SELECT} "
        "FROM hub_org_kb_docs "
        "WHERE kb_id = ? AND deleted_at IS NULL "
        "ORDER BY updated_at DESC",
        (kb_id,),
    ).fetchall()
    return [_doc_row(row) for row in rows]


def get_doc(
    connection: sqlite3.Connection,
    doc_id: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        f"SELECT {_DOC_SELECT} "
        "FROM hub_org_kb_docs WHERE doc_id = ? AND deleted_at IS NULL",
        (doc_id,),
    ).fetchone()
    return _doc_row(row) if row else None


def create_doc(
    connection: sqlite3.Connection,
    *,
    doc_id: str,
    kb_id: str,
    title: str,
    filename: str,
    content_type: str,
    status: str,
    error: str,
    uploaded_by: str,
    rel_path: str,
    customer_key: str = "",
    effective_from: str = "",
    effective_until: str = "",
) -> dict[str, Any]:
    now = utc_now()
    connection.execute(
        "INSERT INTO hub_org_kb_docs("
        "doc_id, kb_id, title, filename, content_type, status, error, "
        "uploaded_by, rel_path, customer_key, effective_from, effective_until, "
        "created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            doc_id,
            kb_id,
            title,
            filename,
            content_type,
            status,
            error,
            uploaded_by,
            rel_path,
            (customer_key or "").strip().lower(),
            (effective_from or "").strip(),
            (effective_until or "").strip(),
            now,
            now,
        ),
    )
    connection.execute(
        "UPDATE hub_org_kbs SET updated_at = ? WHERE kb_id = ?",
        (now, kb_id),
    )
    return get_doc(connection, doc_id) or {}


def update_doc_meta(
    connection: sqlite3.Connection,
    doc_id: str,
    *,
    customer_key: str | None = None,
    effective_from: str | None = None,
    effective_until: str | None = None,
) -> dict[str, Any] | None:
    """Patch optional metadata fields; None means leave unchanged."""
    doc = get_doc(connection, doc_id)
    if doc is None:
        return None
    next_customer = (
        (customer_key or "").strip().lower()
        if customer_key is not None
        else str(doc.get("customer_key") or "")
    )
    next_from = (
        (effective_from or "").strip()
        if effective_from is not None
        else str(doc.get("effective_from") or "")
    )
    next_until = (
        (effective_until or "").strip()
        if effective_until is not None
        else str(doc.get("effective_until") or "")
    )
    connection.execute(
        "UPDATE hub_org_kb_docs SET customer_key = ?, effective_from = ?, "
        "effective_until = ?, updated_at = ? "
        "WHERE doc_id = ? AND deleted_at IS NULL",
        (next_customer, next_from, next_until, utc_now(), doc_id),
    )
    return get_doc(connection, doc_id)


def update_doc_customer_key(
    connection: sqlite3.Connection,
    doc_id: str,
    customer_key: str,
) -> dict[str, Any] | None:
    return update_doc_meta(connection, doc_id, customer_key=customer_key)


def update_doc_status(
    connection: sqlite3.Connection,
    doc_id: str,
    *,
    status: str,
    error: str = "",
) -> None:
    connection.execute(
        "UPDATE hub_org_kb_docs SET status = ?, error = ?, updated_at = ? "
        "WHERE doc_id = ?",
        (status, error, utc_now(), doc_id),
    )


def soft_delete_doc(connection: sqlite3.Connection, doc_id: str) -> bool:
    doc = get_doc(connection, doc_id)
    if doc is None:
        return False
    now = utc_now()
    connection.execute(
        "UPDATE hub_org_kb_docs SET deleted_at = ?, updated_at = ? "
        "WHERE doc_id = ?",
        (now, now, doc_id),
    )
    clear_chunks_for_doc(connection, doc_id)
    return True


def clear_chunks_for_doc(connection: sqlite3.Connection, doc_id: str) -> None:
    rows = connection.execute(
        "SELECT chunk_id FROM hub_org_kb_chunks WHERE doc_id = ?",
        (doc_id,),
    ).fetchall()
    for row in rows:
        connection.execute(
            "DELETE FROM hub_org_kb_fts WHERE chunk_id = ?",
            (str(row["chunk_id"]),),
        )
    connection.execute(
        "DELETE FROM hub_org_kb_chunks WHERE doc_id = ?",
        (doc_id,),
    )


def insert_chunks(
    connection: sqlite3.Connection,
    *,
    kb_id: str,
    doc_id: str,
    title: str,
    chunks: list[str],
) -> int:
    clear_chunks_for_doc(connection, doc_id)
    now = utc_now()
    count = 0
    for index, text in enumerate(chunks):
        body = (text or "").strip()
        if not body:
            continue
        chunk_id = f"{doc_id}:{index}"
        connection.execute(
            "INSERT INTO hub_org_kb_chunks("
            "chunk_id, kb_id, doc_id, chunk_index, text, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (chunk_id, kb_id, doc_id, index, body, now),
        )
        connection.execute(
            "INSERT INTO hub_org_kb_fts(chunk_id, kb_id, doc_id, title, body) "
            "VALUES (?, ?, ?, ?, ?)",
            (chunk_id, kb_id, doc_id, title, body),
        )
        count += 1
    return count


def _customer_acl_sql(
    *,
    doc_alias: str = "d",
    bypass_acl: bool,
    allowed_keys: list[str] | None,
    customer_key_filter: str | None,
) -> tuple[str, list[Any]]:
    """SQL fragment + params restricting customer-tagged docs.

    Empty ``customer_key`` docs are org-wide. Tagged docs require a grant
    unless ``bypass_acl`` (admin / org_kb:manage).
    """
    clauses: list[str] = []
    params: list[Any] = []
    filt = (customer_key_filter or "").strip().lower() or None
    if filt:
        clauses.append(f"{doc_alias}.customer_key = ?")
        params.append(filt)
    if not bypass_acl:
        keys = [k for k in (allowed_keys or []) if k]
        if keys:
            placeholders = ", ".join("?" for _ in keys)
            clauses.append(
                f"({doc_alias}.customer_key = '' OR "
                f"{doc_alias}.customer_key IN ({placeholders}))",
            )
            params.extend(keys)
        else:
            clauses.append(f"{doc_alias}.customer_key = ''")
    if not clauses:
        return "", []
    return " AND " + " AND ".join(clauses), params


def _effective_window_sql(
    *,
    doc_alias: str = "d",
    as_of: str,
    include_expired: bool,
) -> tuple[str, list[Any]]:
    """Only docs whose [effective_from, effective_until] covers ``as_of``.

    Empty bounds are open-ended. ``include_expired`` skips the filter (manage).
    """
    if include_expired:
        return "", []
    day = (as_of or "").strip()[:10]
    if not day:
        day = utc_now()[:10]
    # Compare YYYY-MM-DD lexicographically; empty means unbounded.
    clause = (
        f" AND ({doc_alias}.effective_from = '' OR {doc_alias}.effective_from <= ?) "
        f"AND ({doc_alias}.effective_until = '' OR {doc_alias}.effective_until >= ?)"
    )
    return clause, [day, day]


def search_chunks(
    connection: sqlite3.Connection,
    *,
    query: str,
    kb_id: str | None = None,
    limit: int = 8,
    bypass_acl: bool = False,
    allowed_customer_keys: list[str] | None = None,
    customer_key: str | None = None,
    as_of: str | None = None,
    include_expired: bool = False,
) -> list[dict[str, Any]]:
    needle = (query or "").strip()
    if not needle:
        return []
    limit = max(1, min(int(limit), 20))
    acl_sql, acl_params = _customer_acl_sql(
        bypass_acl=bypass_acl,
        allowed_keys=allowed_customer_keys,
        customer_key_filter=customer_key,
    )
    eff_sql, eff_params = _effective_window_sql(
        as_of=as_of or utc_now()[:10],
        include_expired=include_expired,
    )
    extra_sql = f"{acl_sql}{eff_sql}"
    extra_params = [*acl_params, *eff_params]
    # Retrieval today: FTS5 + BM25 only (no vectors).
    # UPGRADE(embedding): hybrid search — reuse EmbeddingModelConfig /
    # create_embedding_model (same as ReMe); store vectors beside chunks;
    # fuse BM25 ∪ embedding top-k. Do NOT ship in-process model weights;
    # remote API or Ollama. See local/docs/skill-market-product-plan.md §7.2.1.
    # Prefer FTS5; fall back to LIKE if MATCH fails (e.g. special tokens).
    try:
        if kb_id:
            rows = connection.execute(
                "SELECT f.chunk_id, f.kb_id, f.doc_id, f.title, f.body, "
                "d.customer_key, d.effective_from, d.effective_until, "
                "bm25(hub_org_kb_fts) AS score "
                "FROM hub_org_kb_fts f "
                "JOIN hub_org_kb_docs d ON d.doc_id = f.doc_id "
                "WHERE hub_org_kb_fts MATCH ? AND f.kb_id = ? "
                "AND d.deleted_at IS NULL AND d.status = 'ready'"
                f"{extra_sql} "
                "ORDER BY score LIMIT ?",
                (_fts_query(needle), kb_id, *extra_params, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT f.chunk_id, f.kb_id, f.doc_id, f.title, f.body, "
                "d.customer_key, d.effective_from, d.effective_until, "
                "bm25(hub_org_kb_fts) AS score "
                "FROM hub_org_kb_fts f "
                "JOIN hub_org_kb_docs d ON d.doc_id = f.doc_id "
                "JOIN hub_org_kbs k ON k.kb_id = f.kb_id "
                "WHERE hub_org_kb_fts MATCH ? "
                "AND d.deleted_at IS NULL AND d.status = 'ready' "
                "AND k.deleted_at IS NULL"
                f"{extra_sql} "
                "ORDER BY score LIMIT ?",
                (_fts_query(needle), *extra_params, limit),
            ).fetchall()
        if rows:
            return [_hit_row(row) for row in rows]
    except sqlite3.OperationalError:
        pass

    # LIKE fallback: unicode61 FTS often misses Chinese phrases; match any token.
    tokens = _search_tokens(needle)
    like_clauses = " OR ".join(["c.text LIKE ?"] * len(tokens))
    like_params = [f"%{t}%" for t in tokens]
    if kb_id:
        rows = connection.execute(
            "SELECT c.chunk_id, c.kb_id, c.doc_id, d.title, c.text AS body, "
            "d.customer_key, d.effective_from, d.effective_until, 0 AS score "
            "FROM hub_org_kb_chunks c "
            "JOIN hub_org_kb_docs d ON d.doc_id = c.doc_id "
            "WHERE c.kb_id = ? AND d.deleted_at IS NULL "
            f"AND d.status = 'ready' AND ({like_clauses})"
            f"{extra_sql} "
            "ORDER BY c.chunk_index LIMIT ?",
            (kb_id, *like_params, *extra_params, limit),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT c.chunk_id, c.kb_id, c.doc_id, d.title, c.text AS body, "
            "d.customer_key, d.effective_from, d.effective_until, 0 AS score "
            "FROM hub_org_kb_chunks c "
            "JOIN hub_org_kb_docs d ON d.doc_id = c.doc_id "
            "JOIN hub_org_kbs k ON k.kb_id = c.kb_id "
            "WHERE d.deleted_at IS NULL AND d.status = 'ready' "
            f"AND k.deleted_at IS NULL AND ({like_clauses})"
            f"{extra_sql} "
            "ORDER BY c.chunk_index LIMIT ?",
            (*like_params, *extra_params, limit),
        ).fetchall()
    return [_hit_row(row) for row in rows]


def _search_tokens(text: str) -> list[str]:
    """Split query into tokens; keep CJK runs and space-separated words."""
    import re

    cleaned = (text or "").replace('"', " ").strip()
    if not cleaned:
        return []
    parts = re.findall(r"[\u4e00-\u9fff]+|[A-Za-z0-9_]+", cleaned)
    tokens: list[str] = []
    for part in parts:
        if re.fullmatch(r"[\u4e00-\u9fff]+", part) and len(part) >= 4:
            # Prefer bigrams for long Chinese phrases (产品质量 → 产品/品质/质量…).
            for i in range(len(part) - 1):
                tokens.append(part[i : i + 2])
        tokens.append(part)
    # Dedupe while preserving order; keep original needle as last resort.
    seen: set[str] = set()
    out: list[str] = []
    for token in tokens + [cleaned]:
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return out[:24] or [cleaned]


def _fts_query(text: str) -> str:
    tokens = _search_tokens(text)
    if not tokens:
        return text
    # Prefer shorter CJK bigrams for FTS; quote each token.
    return " OR ".join(f'"{t}"' for t in tokens[:12])


def _kb_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "kb_id": str(row["kb_id"]),
        "slug": str(row["slug"]),
        "name": str(row["name"]),
        "kb_type": str(row["kb_type"]),
        "description": str(row["description"] or ""),
        "visibility": str(row["visibility"] or "org"),
        "created_by": str(row["created_by"] or ""),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _doc_row(row: sqlite3.Row) -> dict[str, Any]:
    keys = set(row.keys())
    return {
        "doc_id": str(row["doc_id"]),
        "kb_id": str(row["kb_id"]),
        "title": str(row["title"]),
        "filename": str(row["filename"] or ""),
        "content_type": str(row["content_type"] or ""),
        "status": str(row["status"]),
        "error": str(row["error"] or ""),
        "uploaded_by": str(row["uploaded_by"] or ""),
        "rel_path": str(row["rel_path"] or ""),
        "customer_key": str(row["customer_key"] or "") if "customer_key" in keys else "",
        "effective_from": (
            str(row["effective_from"] or "") if "effective_from" in keys else ""
        ),
        "effective_until": (
            str(row["effective_until"] or "") if "effective_until" in keys else ""
        ),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _hit_row(row: sqlite3.Row) -> dict[str, Any]:
    body = str(row["body"] or "")
    snippet = body if len(body) <= 480 else body[:477] + "..."
    keys = set(row.keys())
    return {
        "chunk_id": str(row["chunk_id"]),
        "kb_id": str(row["kb_id"]),
        "doc_id": str(row["doc_id"]),
        "title": str(row["title"] or ""),
        "body": snippet,
        "snippet": snippet,
        "score": float(row["score"] or 0),
        "customer_key": (
            str(row["customer_key"] or "") if "customer_key" in keys else ""
        ),
        "effective_from": (
            str(row["effective_from"] or "") if "effective_from" in keys else ""
        ),
        "effective_until": (
            str(row["effective_until"] or "") if "effective_until" in keys else ""
        ),
    }


def list_customer_grants(
    connection: sqlite3.Connection,
    *,
    user_id: str | None = None,
) -> list[dict[str, Any]]:
    if user_id:
        rows = connection.execute(
            "SELECT user_id, customer_key, granted_by, created_at "
            "FROM hub_org_kb_customer_grants WHERE user_id = ? "
            "ORDER BY customer_key ASC",
            (user_id,),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT user_id, customer_key, granted_by, created_at "
            "FROM hub_org_kb_customer_grants "
            "ORDER BY user_id ASC, customer_key ASC",
        ).fetchall()
    return [
        {
            "user_id": str(r["user_id"]),
            "customer_key": str(r["customer_key"]),
            "granted_by": str(r["granted_by"] or ""),
            "created_at": str(r["created_at"]),
        }
        for r in rows
    ]


def list_user_customer_keys(
    connection: sqlite3.Connection,
    user_id: str,
) -> list[str]:
    uid = (user_id or "").strip()
    if not uid:
        return []
    rows = connection.execute(
        "SELECT customer_key FROM hub_org_kb_customer_grants "
        "WHERE user_id = ? ORDER BY customer_key ASC",
        (uid,),
    ).fetchall()
    return [str(r["customer_key"]) for r in rows]


def set_user_customer_grants(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    customer_keys: list[str],
    granted_by: str,
) -> list[str]:
    uid = (user_id or "").strip()
    if not uid:
        raise ValueError("user_id 不能为空")
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in customer_keys:
        key = (raw or "").strip().lower()
        if not key or key in seen:
            continue
        if len(key) > 64 or not key[0].isalnum() or any(
            c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in key
        ):
            raise ValueError(f"无效客户标识：{key}")
        seen.add(key)
        cleaned.append(key)
    connection.execute(
        "DELETE FROM hub_org_kb_customer_grants WHERE user_id = ?",
        (uid,),
    )
    now = utc_now()
    for key in cleaned:
        connection.execute(
            "INSERT INTO hub_org_kb_customer_grants("
            "user_id, customer_key, granted_by, created_at) "
            "VALUES (?, ?, ?, ?)",
            (uid, key, granted_by or "", now),
        )
    return cleaned


def list_known_customer_keys(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT DISTINCT customer_key FROM hub_org_kb_docs "
        "WHERE deleted_at IS NULL AND customer_key != '' "
        "ORDER BY customer_key ASC",
    ).fetchall()
    grant_rows = connection.execute(
        "SELECT DISTINCT customer_key FROM hub_org_kb_customer_grants "
        "ORDER BY customer_key ASC",
    ).fetchall()
    keys = {str(r["customer_key"]) for r in rows}
    keys.update(str(r["customer_key"]) for r in grant_rows)
    return sorted(keys)


def list_skill_kb_bindings(
    connection: sqlite3.Connection,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT skill_name, kb_slug, priority "
        "FROM hub_skill_kb_bindings "
        "ORDER BY skill_name ASC, priority ASC, kb_slug ASC",
    ).fetchall()
    by_skill: dict[str, list[str]] = {}
    for row in rows:
        name = str(row["skill_name"])
        by_skill.setdefault(name, []).append(str(row["kb_slug"]))
    return [
        {"skill_name": name, "kb_slugs": slugs}
        for name, slugs in by_skill.items()
    ]


def get_skill_kb_slugs(
    connection: sqlite3.Connection,
    skill_name: str,
) -> list[str]:
    name = (skill_name or "").strip().lower()
    if not name:
        return []
    rows = connection.execute(
        "SELECT kb_slug FROM hub_skill_kb_bindings "
        "WHERE skill_name = ? ORDER BY priority ASC, kb_slug ASC",
        (name,),
    ).fetchall()
    return [str(r["kb_slug"]) for r in rows]


def set_skill_kb_bindings(
    connection: sqlite3.Connection,
    skill_name: str,
    kb_slugs: list[str],
) -> list[str]:
    name = (skill_name or "").strip().lower()
    if not name:
        raise ValueError("skill_name 不能为空")
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in kb_slugs:
        slug = (raw or "").strip().lower()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        cleaned.append(slug)
    connection.execute(
        "DELETE FROM hub_skill_kb_bindings WHERE skill_name = ?",
        (name,),
    )
    for index, slug in enumerate(cleaned):
        connection.execute(
            "INSERT INTO hub_skill_kb_bindings(skill_name, kb_slug, priority) "
            "VALUES (?, ?, ?)",
            (name, slug, index),
        )
    return cleaned


def insert_feedback(
    connection: sqlite3.Connection,
    *,
    feedback_id: str,
    user_id: str,
    chunk_id: str,
    doc_id: str,
    kb_id: str,
    query: str,
    useful: bool,
    note: str = "",
) -> dict[str, Any]:
    now = utc_now()
    connection.execute(
        "INSERT INTO hub_org_kb_feedback("
        "feedback_id, user_id, chunk_id, doc_id, kb_id, query, useful, "
        "note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            feedback_id,
            user_id,
            chunk_id or "",
            doc_id or "",
            kb_id or "",
            (query or "")[:500],
            1 if useful else 0,
            (note or "")[:500],
            now,
        ),
    )
    return {
        "feedback_id": feedback_id,
        "user_id": user_id,
        "chunk_id": chunk_id or "",
        "doc_id": doc_id or "",
        "kb_id": kb_id or "",
        "query": (query or "")[:500],
        "useful": bool(useful),
        "note": (note or "")[:500],
        "created_at": now,
    }


def feedback_stats_for_kb(
    connection: sqlite3.Connection,
    kb_id: str,
) -> dict[str, int]:
    row = connection.execute(
        "SELECT "
        "SUM(CASE WHEN useful = 1 THEN 1 ELSE 0 END) AS up, "
        "SUM(CASE WHEN useful = 0 THEN 1 ELSE 0 END) AS down, "
        "COUNT(*) AS total "
        "FROM hub_org_kb_feedback WHERE kb_id = ?",
        (kb_id,),
    ).fetchone()
    if row is None:
        return {"useful": 0, "not_useful": 0, "total": 0}
    return {
        "useful": int(row["up"] or 0),
        "not_useful": int(row["down"] or 0),
        "total": int(row["total"] or 0),
    }
