#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sync BeeAgent official agents into every QwenPaw Hub runtime.

Official agent packs live in local/official_agents/<id>/.
Each Hub tenant runtime under ~/.qwenpaw/hub/runtimes/*/working receives
workspace files + config.agents.profiles entries so all users can use them.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_DIR = ROOT / "local" / "official_agents"
HUB_RUNTIMES = Path.home() / ".qwenpaw" / "hub" / "runtimes"


def _load_manifest() -> list[dict[str, Any]]:
    manifest_path = OFFICIAL_DIR / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing official pack: {manifest_path}")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return list(data.get("agents") or [])


def _default_agent_json(working: Path) -> dict[str, Any]:
    candidate = working / "workspaces" / "default" / "agent.json"
    if candidate.exists():
        return json.loads(candidate.read_text(encoding="utf-8"))
    return {
        "backend": "qwenpaw",
        "language": "zh",
        "system_prompt_files": ["AGENTS.md", "SOUL.md", "PROFILE.md"],
        "tools": {"builtin_tools": {}},
    }


def _ensure_web_search_deepseek(agent_cfg: dict[str, Any]) -> None:
    tools = agent_cfg.setdefault("tools", {}).setdefault("builtin_tools", {})
    web_search = tools.setdefault(
        "web_search",
        {
            "name": "web_search",
            "enabled": True,
            "description": "Search the web for real-time information",
            "display_to_user": True,
            "async_execution": True,
            "icon": "🔎",
            "config": {},
        },
    )
    config = web_search.setdefault("config", {})
    config["provider"] = "deepseek"
    web_fetch = tools.setdefault(
        "web_fetch",
        {
            "name": "web_fetch",
            "enabled": True,
            "description": "Fetch and read content from a URL",
            "display_to_user": True,
            "async_execution": True,
            "icon": "📥",
            "config": {},
        },
    )
    web_fetch["enabled"] = True


def _copy_credentials(working: Path, agent_id: str) -> None:
    src = working / "workspaces" / "default" / "credentials.yaml"
    dst = working / "workspaces" / agent_id / "credentials.yaml"
    if src.exists() and not dst.exists():
        shutil.copy2(src, dst)


def _sync_runtime(working: Path, agents: list[dict[str, Any]], force: bool) -> int:
    config_path = working / "config.json"
    if not config_path.exists():
        print(f"skip (no config.json): {working}")
        return 0

    config = json.loads(config_path.read_text(encoding="utf-8"))
    agents_cfg = config.setdefault("agents", {})
    profiles = agents_cfg.setdefault("profiles", {})
    order = agents_cfg.setdefault("agent_order", [])
    if not isinstance(order, list):
        order = []
        agents_cfg["agent_order"] = order

    changed = 0
    base = _default_agent_json(working)

    for meta in agents:
        agent_id = meta["id"]
        pack = OFFICIAL_DIR / agent_id
        if not pack.exists():
            print(f"missing pack {agent_id}")
            continue

        ws = working / "workspaces" / agent_id
        ws.mkdir(parents=True, exist_ok=True)

        for filename in ("SOUL.md", "AGENTS.md", "PROFILE.md"):
            src = pack / filename
            dst = ws / filename
            if src.exists() and (force or not dst.exists() or dst.read_text(encoding="utf-8") != src.read_text(encoding="utf-8")):
                shutil.copy2(src, dst)
                changed += 1

        agent_json_path = ws / "agent.json"
        agent_cfg = json.loads(json.dumps(base))  # deep copy via json
        agent_cfg["id"] = agent_id
        agent_cfg["name"] = meta["name"]
        agent_cfg["description"] = meta.get("description") or meta["name"]
        agent_cfg["workspace_dir"] = f"/workspace/workspaces/{agent_id}"
        agent_cfg["language"] = "zh"
        agent_cfg["system_prompt_files"] = ["AGENTS.md", "SOUL.md", "PROFILE.md"]
        # mark as official for humans inspecting the file
        agent_cfg.setdefault("metadata", {})
        if isinstance(agent_cfg["metadata"], dict):
            agent_cfg["metadata"]["official"] = True
            agent_cfg["metadata"]["provider"] = "BeeAgent"
        _ensure_web_search_deepseek(agent_cfg)

        new_text = json.dumps(agent_cfg, ensure_ascii=False, indent=2) + "\n"
        if force or not agent_json_path.exists() or agent_json_path.read_text(encoding="utf-8") != new_text:
            agent_json_path.write_text(new_text, encoding="utf-8")
            changed += 1

        _copy_credentials(working, agent_id)

        profile = profiles.get(agent_id) or {}
        desired = {
            "id": agent_id,
            "workspace_dir": f"/workspace/workspaces/{agent_id}",
            "enabled": True,
            "pinned": True,
        }
        # preserve extra fields if any
        profile.update(desired)
        if profiles.get(agent_id) != profile:
            profiles[agent_id] = profile
            changed += 1

        if agent_id not in order:
            order.append(agent_id)
            changed += 1

    # also keep root tools web_search on deepseek if present
    try:
        root_tools = config.setdefault("tools", {}).setdefault("builtin_tools", {})
        ws_cfg = root_tools.setdefault("web_search", {"name": "web_search", "enabled": True, "config": {}})
        ws_cfg.setdefault("config", {})["provider"] = "deepseek"
    except Exception:
        pass

    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"synced {working} (+{changed})")
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
        help="Overwrite existing official agent files",
    )
    args = parser.parse_args()

    agents = _load_manifest()
    if not agents:
        raise SystemExit("official manifest is empty")

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
        total += _sync_runtime(working, agents, force=args.force)
    print(f"done. runtimes={len(targets)} changes={total}")


if __name__ == "__main__":
    main()
