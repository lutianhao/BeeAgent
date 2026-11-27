#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply BeeAgent Hub user_sync_roster.yaml (iteration desired-state).

Re-asserts per-user RBAC role bindings from the roster, optionally ensures
org-skill installs by name, and prints a refresh checklist.

Typical flow (via manage.sh):
  apply_user_sync_roster.py
  sync_official_skills.py --force
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML required: pip install pyyaml") from exc


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROSTER = ROOT / "local" / "hub_rbac" / "user_sync_roster.yaml"
HUB_CONTROL_DB = Path.home() / ".qwenpaw" / "hub" / "control.db"


def _load_roster(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"invalid roster: {path}")
    if int(data.get("schema_version") or 0) < 1:
        raise SystemExit(f"roster schema_version missing: {path}")
    return data


def _connect(db: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db, timeout=60.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _users_by_username(con: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    rows = con.execute(
        "SELECT user_id, username, role, disabled, deleted_at "
        "FROM hub_users WHERE deleted_at IS NULL",
    ).fetchall()
    return {str(r["username"]): r for r in rows}


def _ensure_system_roles(con: sqlite3.Connection) -> None:
    from qwenpaw.hub.rbac import store
    from qwenpaw.hub.rbac.catalog import BUILTIN_ROLES

    store.ensure_rbac_schema(con)
    for role_id, meta in BUILTIN_ROLES.items():
        store.upsert_role(
            con,
            role_id=role_id,
            name=str(meta["name"]),
            description=str(meta.get("description") or ""),
            permissions=list(meta.get("permissions") or []),
            is_system=True,
        )


def _apply_user_roles(
    con: sqlite3.Connection,
    *,
    user_id: str,
    username: str,
    role_ids: list[str],
    assigned_by: str,
    dry_run: bool,
) -> list[str]:
    from qwenpaw.hub.rbac import store

    current = store.get_user_role_ids(con, user_id)
    wanted = list(role_ids)
    if current == wanted:
        print(f"  roles unchanged: {wanted or '(none / hub-admin)'}")
        return current
    print(f"  roles {current} → {wanted or '(none / hub-admin)'}")
    if dry_run:
        return wanted
    return store.set_user_roles(
        con,
        user_id,
        wanted,
        assigned_by=assigned_by,
    )


def _skill_id_by_name(con: sqlite3.Connection, name: str) -> str | None:
    row = con.execute(
        "SELECT skill_id FROM hub_org_skills "
        "WHERE name = ? AND status != 'deleted' "
        "ORDER BY updated_at DESC LIMIT 1",
        (name,),
    ).fetchone()
    return str(row["skill_id"]) if row else None


def _ensure_org_installs(
    *,
    username: str,
    user_id: str,
    skill_names: list[str],
    dry_run: bool,
) -> int:
    if not skill_names:
        return 0
    from qwenpaw.hub.org_skills.service import OrgSkillsService

    service = OrgSkillsService(HUB_CONTROL_DB)
    changed = 0
    for name in skill_names:
        with _connect(HUB_CONTROL_DB) as con:
            skill_id = _skill_id_by_name(con, name)
        if not skill_id:
            print(f"  ensure install skip (missing skill): {name}")
            continue
        if dry_run:
            print(f"  would ensure install: {name} ({skill_id[:8]}…)")
            continue
        try:
            service.install_for_user(
                skill_id,
                user_id=user_id,
                is_hub_member=True,
                force=False,
            )
            print(f"  ensured org skill install: {name}")
            changed += 1
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # Already installed / pinned / permission — keep going.
            print(f"  install {name} for {username}: {exc}")
    return changed


def apply_roster(
    roster_path: Path,
    *,
    dry_run: bool = False,
    skip_installs: bool = False,
) -> int:
    roster = _load_roster(roster_path)
    users_cfg: dict[str, Any] = dict(roster.get("users") or {})
    default_role = str(roster.get("default_role") or "bee.member")
    phase = roster.get("phase") or ""
    print(f"roster: {roster_path}")
    print(f"phase: {phase}  default_role: {default_role}")
    if not HUB_CONTROL_DB.exists():
        raise SystemExit(f"control.db missing: {HUB_CONTROL_DB}")

    changed = 0
    with _connect(HUB_CONTROL_DB) as con:
        _ensure_system_roles(con)
        by_name = _users_by_username(con)
        admin_row = by_name.get("admin")
        assigned_by = str(admin_row["user_id"] if admin_row else "roster-apply")

        # Warn about DB users not in roster
        for username in sorted(by_name):
            if username not in users_cfg:
                print(
                    f"! {username}: in DB but not in roster "
                    f"→ will bind {default_role} if no roles",
                )

        for username, cfg in users_cfg.items():
            row = by_name.get(username)
            print(f"\n## {username}")
            if row is None:
                print("  SKIP: user not in hub_users (create account first)")
                continue
            if int(row["disabled"] or 0):
                print("  SKIP: disabled")
                continue

            hub_role = str(row["role"] or "user")
            expect_hub = str(cfg.get("hub_role") or "user")
            if hub_role != expect_hub:
                print(
                    f"  warn hub_role DB={hub_role} roster={expect_hub} "
                    "(hub_role not auto-changed)",
                )

            if expect_hub == "admin" or hub_role == "admin":
                print("  hub admin: RBAC bypass; runtime still syncs all skills")
                role_ids: list[str] = list(cfg.get("rbac_roles") or [])
            else:
                role_ids = list(cfg.get("rbac_roles") or [default_role])

            before = None
            from qwenpaw.hub.rbac import store

            before = store.get_user_role_ids(con, str(row["user_id"]))
            after = _apply_user_roles(
                con,
                user_id=str(row["user_id"]),
                username=username,
                role_ids=role_ids,
                assigned_by=assigned_by,
                dry_run=dry_run,
            )
            if before != after:
                changed += 1

            sync = dict(cfg.get("sync") or {})
            print(
                "  sync:"
                f" skills={sync.get('official_skills')}"
                f" tools={sync.get('official_tools')}"
                f" deepseek={sync.get('deepseek_defaults')}"
                f" persona={sync.get('persona_defaults')}",
            )
            notes = list(cfg.get("refresh_notes") or [])
            for note in notes:
                print(f"  · {note}")

        # Unlisted users → ensure default_role
        for username, row in sorted(by_name.items()):
            if username in users_cfg:
                continue
            if str(row["role"]) == "admin":
                continue
            from qwenpaw.hub.rbac import store

            current = store.get_user_role_ids(con, str(row["user_id"]))
            if current:
                continue
            print(f"\n## {username} (unlisted)")
            _apply_user_roles(
                con,
                user_id=str(row["user_id"]),
                username=username,
                role_ids=[default_role],
                assigned_by=assigned_by,
                dry_run=dry_run,
            )
            changed += 1

        if not dry_run:
            con.commit()

    if not skip_installs:
        print("\n=== ensure org skill installs ===")
        with _connect(HUB_CONTROL_DB) as con:
            by_name = _users_by_username(con)
        for username, cfg in users_cfg.items():
            row = by_name.get(username)
            if row is None:
                continue
            names = list(cfg.get("ensure_org_skill_installs") or [])
            if not names:
                continue
            print(f"\n## {username} installs")
            changed += _ensure_org_installs(
                username=username,
                user_id=str(row["user_id"]),
                skill_names=names,
                dry_run=dry_run,
            )

    print(f"\ndone. roster_changes={changed} dry_run={dry_run}")
    return changed


def dump_effective() -> None:
    """Print current DB entitlements for quick diff vs roster."""
    from qwenpaw.hub.rbac import RbacService

    rbac = RbacService(HUB_CONTROL_DB)
    with _connect(HUB_CONTROL_DB) as con:
        rows = con.execute(
            "SELECT user_id, username, role FROM hub_users "
            "WHERE deleted_at IS NULL ORDER BY username",
        ).fetchall()
    for row in rows:
        ent = rbac.entitlements(
            str(row["user_id"]),
            is_hub_admin=str(row["role"]) == "admin",
        )
        print(
            json.dumps(
                {
                    "username": row["username"],
                    "hub_role": row["role"],
                    "roles": ent.get("roles"),
                    "allowed_skills": ent.get("allowed_skills"),
                    "allowed_tools": ent.get("allowed_tools"),
                    "permissions": ent.get("permissions"),
                },
                ensure_ascii=False,
            ),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roster",
        type=Path,
        default=DEFAULT_ROSTER,
        help=f"roster yaml (default: {DEFAULT_ROSTER})",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-installs",
        action="store_true",
        help="Only apply RBAC; skip org-skill install ensure",
    )
    parser.add_argument(
        "--dump",
        action="store_true",
        help="Print current entitlements JSON lines and exit",
    )
    args = parser.parse_args()
    if args.dump:
        dump_effective()
        return
    if not args.roster.exists():
        raise SystemExit(f"roster not found: {args.roster}")
    apply_roster(
        args.roster,
        dry_run=args.dry_run,
        skip_installs=args.skip_installs,
    )


if __name__ == "__main__":
    main()
