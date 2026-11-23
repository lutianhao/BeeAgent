# -*- coding: utf-8 -*-
"""Read personal-runtime token_usage.json for Hub admin / RBAC mirrors.

BeeAgent personal runtimes usually call LLM providers directly, so the Hub
model-gateway ledger (hub_model_requests) stays empty. Local token totals
still land in each runtime's working/token_usage.json — this helper surfaces
those absolute totals for admin stats.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def personal_working_dir(
    connection: sqlite3.Connection,
    user_id: str,
) -> Path | None:
    row = connection.execute(
        "SELECT storage_json FROM runtimes "
        "WHERE owner_user_id = ? AND deleted_at IS NULL "
        "ORDER BY created_at ASC LIMIT 1",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        storage = json.loads(str(row["storage_json"] or "{}"))
    except Exception:  # pylint: disable=broad-exception-caught
        return None
    working = str(storage.get("working_dir") or "").strip()
    if not working:
        return None
    path = Path(working)
    return path if path.is_dir() else None


def load_token_usage_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # pylint: disable=broad-exception-caught
        return {}
    return data if isinstance(data, dict) else {}


def day_token_total(day_map: Any) -> int:
    if not isinstance(day_map, dict):
        return 0
    total = 0
    for entry in day_map.values():
        if not isinstance(entry, dict):
            continue
        total += int(entry.get("prompt_tokens") or 0)
        total += int(entry.get("completion_tokens") or 0)
    return total


def day_call_count(day_map: Any) -> int:
    if not isinstance(day_map, dict):
        return 0
    total = 0
    for entry in day_map.values():
        if not isinstance(entry, dict):
            continue
        total += int(entry.get("call_count") or 0)
    return total


def sum_tokens_for_day(usage_path: Path, usage_date: str) -> int | None:
    """Return absolute tokens for *usage_date*, or None if file missing."""
    if not usage_path.is_file():
        return None
    data = load_token_usage_file(usage_path)
    if not data and not usage_path.is_file():
        return None
    return day_token_total(data.get(usage_date))


def iter_day_totals(usage_path: Path) -> dict[str, int]:
    """Map YYYY-MM-DD -> absolute token total from a usage file."""
    data = load_token_usage_file(usage_path)
    out: dict[str, int] = {}
    for key, value in data.items():
        if not isinstance(key, str) or len(key) < 10:
            continue
        if key[4] != "-" or key[7] != "-":
            continue
        out[key] = day_token_total(value)
    return out


def period_totals_for_user(
    connection: sqlite3.Connection,
    user_id: str,
    period: str,
) -> dict[str, int]:
    """Sum runtime tokens for a YYYY-MM period.

    Returns charged/actual/requests-compatible counters (reserved=0).
    """
    working = personal_working_dir(connection, user_id)
    if working is None:
        return {"charged": 0, "actual": 0, "requests": 0}
    data = load_token_usage_file(working / "token_usage.json")
    charged = 0
    requests = 0
    prefix = period  # e.g. 2026-11
    for key, value in data.items():
        if not isinstance(key, str) or not key.startswith(prefix):
            continue
        charged += day_token_total(value)
        requests += day_call_count(value)
    return {
        "charged": charged,
        "actual": charged,
        "requests": requests,
    }


def daily_totals_for_period(
    connection: sqlite3.Connection,
    period: str,
) -> dict[str, int]:
    """Aggregate all users' runtime tokens by date within *period*."""
    daily: dict[str, int] = {}
    rows = connection.execute(
        "SELECT owner_user_id, storage_json FROM runtimes "
        "WHERE deleted_at IS NULL",
    ).fetchall()
    seen_users: set[str] = set()
    for row in rows:
        user_id = str(row["owner_user_id"])
        if user_id in seen_users:
            continue
        seen_users.add(user_id)
        try:
            storage = json.loads(str(row["storage_json"] or "{}"))
        except Exception:  # pylint: disable=broad-exception-caught
            continue
        working = str(storage.get("working_dir") or "").strip()
        if not working:
            continue
        path = Path(working) / "token_usage.json"
        for day, tokens in iter_day_totals(path).items():
            if not day.startswith(period):
                continue
            daily[day] = daily.get(day, 0) + tokens
    return daily


def usage_detail_rows(
    connection: sqlite3.Connection,
    *,
    start_date: str,
    end_date: str,
    usernames: dict[str, str],
) -> list[dict[str, Any]]:
    """Synthetic analytics rows from runtime usage files (date/user/model)."""
    rows_out: list[dict[str, Any]] = []
    runtime_rows = connection.execute(
        "SELECT owner_user_id, storage_json FROM runtimes "
        "WHERE deleted_at IS NULL ORDER BY created_at ASC",
    ).fetchall()
    seen_users: set[str] = set()
    for row in runtime_rows:
        user_id = str(row["owner_user_id"])
        if user_id in seen_users:
            continue
        seen_users.add(user_id)
        try:
            storage = json.loads(str(row["storage_json"] or "{}"))
        except Exception:  # pylint: disable=broad-exception-caught
            continue
        working = str(storage.get("working_dir") or "").strip()
        if not working:
            continue
        data = load_token_usage_file(Path(working) / "token_usage.json")
        username = usernames.get(user_id, user_id)
        for day, day_map in data.items():
            if not isinstance(day, str) or not isinstance(day_map, dict):
                continue
            if day < start_date or day > end_date:
                continue
            for model_key, entry in day_map.items():
                if not isinstance(entry, dict):
                    continue
                prompt = int(entry.get("prompt_tokens") or 0)
                completion = int(entry.get("completion_tokens") or 0)
                tokens = prompt + completion
                if tokens <= 0 and int(entry.get("call_count") or 0) <= 0:
                    continue
                model_id = str(model_key)
                model_name = str(
                    entry.get("model_name")
                    or entry.get("model")
                    or "",
                ).strip()
                if not model_name:
                    # Keys may be "provider:model" or agent\\x1fprovider\\x1fmodel.
                    parts = [
                        p
                        for p in model_id.replace("\x1f", ":").split(":")
                        if p
                    ]
                    model_name = parts[-1] if parts else model_id
                rows_out.append(
                    {
                        "date": day,
                        "user_id": user_id,
                        "username": username,
                        "model_id": model_id,
                        "model_name": model_name,
                        "requests": int(entry.get("call_count") or 0),
                        "charged": tokens,
                        "actual": tokens,
                        "reserved": 0,
                        "conservative": 0,
                        "failures": 0,
                    },
                )
    return rows_out
