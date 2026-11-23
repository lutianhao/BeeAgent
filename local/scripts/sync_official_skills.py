#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sync BeeAgent official skills into every QwenPaw Hub runtime.

Official skill packs live in local/official_skills/<name>/SKILL.md.
Each Hub tenant runtime under ~/.qwenpaw/hub/runtimes/*/working receives:
  - skill_pool/<name>/ copy
  - skill_pool/skill.json entry
  - workspaces/default/skill.json enabled entry
  - workspaces/default/{SOUL,AGENTS,PROFILE}.md from local/official_default/
  - legacy expert agent profiles disabled (kept on disk, hidden from picker)

Default agent remains the sole general-purpose agent.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_DIR = ROOT / "local" / "official_skills"
OFFICIAL_DEFAULT = ROOT / "local" / "official_default"
HUB_RUNTIMES = Path.home() / ".qwenpaw" / "hub" / "runtimes"
HUB_CONTROL_DB = Path.home() / ".qwenpaw" / "hub" / "control.db"
DEFAULT_PERSONA_FILES = ("SOUL.md", "AGENTS.md", "PROFILE.md")

LEGACY_AGENT_IDS = {
    "wangping_huashu",
    "shensu_chegao",
    "yuqing_yanpan",
    "yuan_xiezhuan",
    "shiqian_pinggu",
    "paicha_fangan",
    "weike_wenan",
    "yanlian_jiaoben",
    "koujing_xiezhuan",
}

KEEP_IN_ORDER = {"default", "QwenPaw_QA_Agent_0.2"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _load_manifest() -> list[dict[str, Any]]:
    path = OFFICIAL_DIR / "manifest.json"
    if not path.exists():
        raise SystemExit(f"missing official skills: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("skills") or [])


def _parse_skill_md(skill_dir: Path) -> dict[str, Any]:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"missing frontmatter: {skill_dir}")
    end = text.find("\n---", 3)
    if end < 0:
        raise ValueError(f"bad frontmatter: {skill_dir}")
    fm = text[3:end]
    name_m = re.search(r"^name:\s*(.+)$", fm, re.M)
    desc_m = re.search(r'^description:\s*"(.*)"\s*$', fm, re.M) or re.search(
        r"^description:\s*(.+)$", fm, re.M
    )
    emoji_m = re.search(r'emoji:\s*"([^"]*)"', fm)
    name = (name_m.group(1).strip() if name_m else skill_dir.name).strip("\"'")
    desc = (desc_m.group(1).strip() if desc_m else name).strip("\"'")
    emoji = emoji_m.group(1) if emoji_m else "🛠️"
    return {
        "name": name,
        "description": desc,
        "emoji": emoji,
        "version_text": "1.0",
    }


def _pool_entry(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": meta["name"],
        "description": meta["description"],
        "version_text": meta.get("version_text") or "1.0",
        "emoji": meta.get("emoji") or "🛠️",
        "commit_text": "",
        "source": "customized",
        "protected": False,
        "requirements": {
            "require_bins": [],
            "require_envs": [],
            "require_mcps": [],
        },
        "updated_at": _now(),
        "installation_origin": {
            "kind": "local",
            "provider": "BeeAgent",
            "label": "official_skills",
        },
        "installed_from": str(OFFICIAL_DIR / meta["name"]),
    }


def _workspace_entry(meta: dict[str, Any], pool_meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": True,
        "channels": ["all"],
        "preload": False,
        "source": "customized",
        "metadata": {
            "name": pool_meta["name"],
            "description": pool_meta["description"],
            "version_text": pool_meta["version_text"],
            "emoji": pool_meta["emoji"],
            "commit_text": "",
            "source": "customized",
            "protected": False,
            "requirements": pool_meta["requirements"],
            "updated_at": pool_meta["updated_at"],
        },
        "requirements": pool_meta["requirements"],
        "updated_at": pool_meta["updated_at"],
        "config": {},
        "installation_origin": pool_meta.get("installation_origin"),
        "installed_from": pool_meta.get("installed_from"),
    }


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sync_skill_pool(working: Path, skills: list[dict[str, Any]], force: bool) -> int:
    pool = working / "skill_pool"
    pool.mkdir(parents=True, exist_ok=True)
    manifest_path = pool / "skill.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "schema_version": "skill-pool-manifest.v1",
            "version": 0,
            "skills": {},
            "builtin_skill_names": [],
        }
    manifest.setdefault("skills", {})
    changed = 0

    for item in skills:
        name = item["name"]
        src = OFFICIAL_DIR / name
        if not (src / "SKILL.md").exists():
            print(f"missing skill pack: {src}")
            continue
        dst = pool / name
        dst.mkdir(parents=True, exist_ok=True)
        src_md = (src / "SKILL.md").read_text(encoding="utf-8")
        dst_md = dst / "SKILL.md"
        if force or not dst_md.exists() or dst_md.read_text(encoding="utf-8") != src_md:
            dst_md.write_text(src_md, encoding="utf-8")
            changed += 1

        parsed = _parse_skill_md(src)
        entry = _pool_entry(parsed)
        # preserve config if any
        existing = manifest["skills"].get(name) or {}
        if isinstance(existing, dict) and "config" in existing:
            entry["config"] = existing["config"]
        if force or existing != entry:
            # compare loosely on content fields
            if (
                force
                or existing.get("description") != entry["description"]
                or existing.get("source") != "customized"
                or not dst_md.exists()
            ):
                manifest["skills"][name] = entry
                changed += 1
            else:
                # still refresh description/emoji from pack
                existing.update(
                    {
                        "description": entry["description"],
                        "emoji": entry["emoji"],
                        "version_text": entry["version_text"],
                        "source": "customized",
                        "updated_at": entry["updated_at"],
                        "installation_origin": entry["installation_origin"],
                        "installed_from": entry["installed_from"],
                    }
                )
                manifest["skills"][name] = existing

    manifest["version"] = int(datetime.now(timezone.utc).timestamp() * 1000)
    _write_json(manifest_path, manifest)
    return changed


def _resolve_rbac_entitlements(working: Path) -> dict[str, Any] | None:
    """Return Hub RBAC entitlements for the runtime owner, or None."""
    try:
        import sys

        qwenpaw_src = ROOT / "QwenPaw" / "src"
        if str(qwenpaw_src) not in sys.path:
            sys.path.insert(0, str(qwenpaw_src))
        from qwenpaw.hub.rbac import RbacService
    except Exception as exc:
        print(f"rbac import skipped: {exc}")
        return None
    if not HUB_CONTROL_DB.exists():
        return None
    runtime_id = working.parent.name  # .../runtimes/<id>/working
    try:
        import sqlite3

        conn = sqlite3.connect(HUB_CONTROL_DB)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT owner_user_id FROM runtimes WHERE runtime_id = ? AND deleted_at IS NULL",
            (runtime_id,),
        ).fetchone()
        user_row = None
        if row is not None:
            user_row = conn.execute(
                "SELECT role FROM hub_users WHERE user_id = ?",
                (row["owner_user_id"],),
            ).fetchone()
        conn.close()
        if row is None or user_row is None:
            return None
        rbac = RbacService(HUB_CONTROL_DB)
        return rbac.entitlements(
            str(row["owner_user_id"]),
            is_hub_admin=(str(user_row["role"]) == "admin"),
        )
    except Exception as exc:
        print(f"rbac resolve skipped for {runtime_id}: {exc}")
        return None


def _resolve_allowed_skills(working: Path) -> list[str] | None:
    ent = _resolve_rbac_entitlements(working)
    if ent is None:
        return None
    return list(ent.get("allowed_skills") or [])


def _apply_tool_acl(working: Path, allowed_tools: list[str] | None) -> int:
    """Enable/disable controllable builtin tools from RBAC."""
    if allowed_tools is None:
        return 0
    allowed = set(allowed_tools)
    changed = 0

    def patch_builtin(tools_node: dict[str, Any]) -> int:
        local = 0
        builtin = tools_node.setdefault("builtin_tools", {})
        if not isinstance(builtin, dict):
            return 0
        for name in ("web_search", "web_fetch"):
            entry = builtin.get(name)
            if not isinstance(entry, dict):
                entry = {"name": name, "enabled": True, "config": {}}
                builtin[name] = entry
            want = name in allowed
            if entry.get("enabled") != want:
                entry["enabled"] = want
                local += 1
            if name == "web_search":
                tool_cfg = entry.setdefault("config", {})
                if isinstance(tool_cfg, dict) and tool_cfg.get("provider") != "deepseek":
                    tool_cfg["provider"] = "deepseek"
                    local += 1
        return local

    targets = [working / "config.json", working / "workspaces" / "default" / "agent.json"]
    for path in targets:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        local = 0
        tools = data.setdefault("tools", {})
        if isinstance(tools, dict):
            local += patch_builtin(tools)
        if path.name == "config.json":
            profiles = (
                data.get("agents", {}).get("profiles", {})
                if isinstance(data.get("agents"), dict)
                else {}
            )
            if isinstance(profiles, dict):
                for profile in profiles.values():
                    if not isinstance(profile, dict):
                        continue
                    ptools = profile.setdefault("tools", {})
                    if isinstance(ptools, dict):
                        local += patch_builtin(ptools)
        if local:
            _write_json(path, data)
            changed += local
    return changed


def _enable_on_default(
    working: Path,
    skills: list[dict[str, Any]],
    force: bool,
    allowed_skills: list[str] | None = None,
) -> int:
    ws = working / "workspaces" / "default"
    if not ws.exists():
        return 0
    skill_json = ws / "skill.json"
    if skill_json.exists():
        data = json.loads(skill_json.read_text(encoding="utf-8"))
    else:
        data = {
            "schema_version": "workspace-skill-manifest.v1",
            "version": 0,
            "skills": {},
        }
    data.setdefault("skills", {})
    pool_manifest = json.loads((working / "skill_pool" / "skill.json").read_text(encoding="utf-8"))
    pool_skills = pool_manifest.get("skills") or {}
    changed = 0

    # also copy into workspace skills/ so agent can load without pool-only quirks
    skills_dir = ws / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    for item in skills:
        name = item["name"]
        pool_meta = pool_skills.get(name)
        if not isinstance(pool_meta, dict):
            continue
        src = working / "skill_pool" / name / "SKILL.md"
        dst_dir = skills_dir / name
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / "SKILL.md"
        if src.exists() and (
            force or not dst.exists() or dst.read_text(encoding="utf-8") != src.read_text(encoding="utf-8")
        ):
            shutil.copy2(src, dst)
            changed += 1

        entry = _workspace_entry(item, pool_meta)
        if allowed_skills is not None:
            entry["enabled"] = name in set(allowed_skills)
        existing = data["skills"].get(name)
        if force or existing != entry:
            data["skills"][name] = entry
            changed += 1

    data["version"] = int(datetime.now(timezone.utc).timestamp() * 1000)
    _write_json(skill_json, data)
    return changed


def _disable_legacy_agents(working: Path) -> int:
    config_path = working / "config.json"
    if not config_path.exists():
        return 0
    config = json.loads(config_path.read_text(encoding="utf-8"))
    agents_cfg = config.setdefault("agents", {})
    profiles = agents_cfg.setdefault("profiles", {})
    order = agents_cfg.get("agent_order") or []
    changed = 0

    for agent_id in list(LEGACY_AGENT_IDS):
        profile = profiles.get(agent_id)
        if not isinstance(profile, dict):
            continue
        desired = dict(profile)
        desired["enabled"] = False
        desired["pinned"] = False
        if profiles.get(agent_id) != desired:
            profiles[agent_id] = desired
            changed += 1

    new_order = [a for a in order if a not in LEGACY_AGENT_IDS]
    # keep default first
    if "default" in new_order:
        new_order = ["default"] + [a for a in new_order if a != "default"]
    elif (working / "workspaces" / "default").exists():
        new_order = ["default"] + new_order
    if new_order != order:
        agents_cfg["agent_order"] = new_order
        changed += 1

    # Ensure default profile enabled
    default_profile = profiles.get("default") or {
        "id": "default",
        "workspace_dir": "/workspace/workspaces/default",
    }
    default_profile["id"] = "default"
    default_profile["enabled"] = True
    default_profile["pinned"] = True
    if profiles.get("default") != default_profile:
        profiles["default"] = default_profile
        changed += 1

    if changed:
        _write_json(config_path, config)
    return changed


def _ensure_default_general(working: Path, force: bool) -> int:
    """Keep default agent as BeeAgent general persona + official SOUL/AGENTS."""
    ws = working / "workspaces" / "default"
    if not ws.exists():
        return 0
    changed = 0

    for filename in DEFAULT_PERSONA_FILES:
        src = OFFICIAL_DEFAULT / filename
        if not src.exists():
            print(f"missing default persona: {src}")
            continue
        dst = ws / filename
        text = src.read_text(encoding="utf-8")
        if force or not dst.exists() or dst.read_text(encoding="utf-8") != text:
            dst.write_text(text, encoding="utf-8")
            changed += 1

    agent_json_path = ws / "agent.json"
    if agent_json_path.exists():
        agent = json.loads(agent_json_path.read_text(encoding="utf-8"))
        want_name = "BeeAgent 通用智能体"
        want_desc = "通用智能体；声誉管理等专项能力以 Skills 形式按需启用"
        want_files = ["AGENTS.md", "SOUL.md", "PROFILE.md"]
        dirty = (
            force
            or agent.get("name") != want_name
            or agent.get("description") != want_desc
            or agent.get("system_prompt_files") != want_files
        )
        if dirty:
            agent["name"] = want_name
            agent["description"] = want_desc
            agent["system_prompt_files"] = want_files
            agent.setdefault("metadata", {})
            if isinstance(agent["metadata"], dict):
                agent["metadata"]["official"] = True
                agent["metadata"]["provider"] = "BeeAgent"
            _write_json(agent_json_path, agent)
            changed += 1

    return changed


def _provision_deepseek_defaults(working: Path) -> int:
    """Ensure DeepSeek provider/model + web tools for this runtime.

    Calls provider/tool helpers directly (not ``ensure_runtime_defaults``) to
    avoid re-entering official-skills sync via subprocess.
    """
    try:
        import os
        import sys

        os.environ["BEEAGENT_SKILL_SYNC"] = "1"
        qwenpaw_src = ROOT / "QwenPaw" / "src"
        if str(qwenpaw_src) not in sys.path:
            sys.path.insert(0, str(qwenpaw_src))
        from qwenpaw.hub.beeagent_defaults import (
            ensure_provider_secrets,
            ensure_tool_defaults,
        )
    except Exception as exc:
        print(f"  deepseek defaults import skipped: {exc}")
        return 0
    secret_dir = working.parent / "secrets"
    try:
        result = ensure_provider_secrets(secret_dir)
        tool_changes = ensure_tool_defaults(working)
    except Exception as exc:
        print(f"  deepseek defaults failed: {exc}")
        return 0
    changed = int(bool(result.get("provider"))) + int(
        bool(result.get("active_model")),
    ) + int(tool_changes or 0)
    if result.get("skipped"):
        print(f"  deepseek defaults skipped: {result.get('reason')}")
    elif changed:
        print(
            "  deepseek defaults:"
            f" provider={result.get('provider')}"
            f" active_model={result.get('active_model')}"
            f" tools={tool_changes}",
        )
    return changed


def _sync_runtime(working: Path, skills: list[dict[str, Any]], force: bool) -> int:
    if not (working / "config.json").exists():
        print(f"skip (no config.json): {working}")
        return 0
    changed = 0
    changed += _provision_deepseek_defaults(working)
    ent = _resolve_rbac_entitlements(working)
    allowed = list(ent.get("allowed_skills") or []) if ent is not None else None
    allowed_tools = list(ent.get("allowed_tools") or []) if ent is not None else None
    if allowed is not None:
        print(f"  rbac allowed_skills={allowed}")
    if allowed_tools is not None:
        print(f"  rbac allowed_tools={allowed_tools}")
    changed += _sync_skill_pool(working, skills, force)
    changed += _enable_on_default(working, skills, force, allowed_skills=allowed)
    # If RBAC has no tool ACL yet, still ensure DeepSeek tool defaults above.
    # When ACL exists, re-apply enable/disable + keep web_search provider=deepseek.
    changed += _apply_tool_acl(working, allowed_tools)
    changed += _disable_legacy_agents(working)
    changed += _ensure_default_general(working, force)
    print(f"synced skills → {working} (+{changed})")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime",
        action="append",
        default=[],
        help="Specific runtime working dir; default=all hub runtimes",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing official skill files",
    )
    args = parser.parse_args()

    skills = _load_manifest()
    if not skills:
        raise SystemExit("official skills manifest is empty")

    targets: list[Path] = []
    if args.runtime:
        targets = [Path(p).expanduser().resolve() for p in args.runtime]
    else:
        if not HUB_RUNTIMES.exists():
            raise SystemExit(f"no hub runtimes at {HUB_RUNTIMES}")
        for runtime_dir in sorted(HUB_RUNTIMES.iterdir()):
            working = runtime_dir / "working"
            if working.exists():
                targets.append(working)

    if not targets:
        raise SystemExit("no runtime working dirs found")

    total = 0
    for working in targets:
        total += _sync_runtime(working, skills, force=args.force)
    print(f"done. runtimes={len(targets)} changes={total}")


if __name__ == "__main__":
    main()
