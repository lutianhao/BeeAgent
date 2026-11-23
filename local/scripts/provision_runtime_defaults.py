#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Provision DeepSeek defaults for all Hub personal runtimes.

Sets:
  - secrets/providers/builtin/deepseek.json
  - secrets/providers/active_model.json → deepseek / deepseek-flash
  - web_search (provider=deepseek) + web_fetch in config/agent.json

Requires DEEPSEEK_API_KEY in the environment (manage.sh loads
local/secrets/deepseek.env).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HUB_RUNTIMES = Path.home() / ".qwenpaw" / "hub" / "runtimes"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime",
        action="append",
        default=[],
        help="Runtime root or working dir; default=all hub runtimes",
    )
    args = parser.parse_args()

    qwenpaw_src = ROOT / "QwenPaw" / "src"
    sys.path.insert(0, str(qwenpaw_src))
    from qwenpaw.hub.beeagent_defaults import ensure_runtime_defaults

    targets: list[tuple[Path, Path]] = []
    if args.runtime:
        for raw in args.runtime:
            path = Path(raw).expanduser().resolve()
            if path.name == "working":
                targets.append((path.parent / "secrets", path))
            elif (path / "working").exists():
                targets.append((path / "secrets", path / "working"))
            else:
                raise SystemExit(f"not a hub runtime path: {path}")
    else:
        if not HUB_RUNTIMES.exists():
            raise SystemExit(f"no hub runtimes at {HUB_RUNTIMES}")
        for runtime_dir in sorted(HUB_RUNTIMES.iterdir()):
            working = runtime_dir / "working"
            secrets = runtime_dir / "secrets"
            if working.exists() and secrets.exists():
                targets.append((secrets, working))

    if not targets:
        raise SystemExit("no runtime targets found")

    total = 0
    for secret_dir, working in targets:
        result = ensure_runtime_defaults(secret_dir, working)
        changed = (
            int(bool(result.get("provider")))
            + int(bool(result.get("active_model")))
            + int(result.get("tool_changes") or 0)
        )
        total += changed
        print(
            f"{working.parent.name}: provider={result.get('provider')} "
            f"active_model={result.get('active_model')} "
            f"tools={result.get('tool_changes')} "
            f"skipped={result.get('skipped')} {result.get('reason') or ''}".rstrip(),
        )
    print(f"done. runtimes={len(targets)} changes={total}")


if __name__ == "__main__":
    main()
