# -*- coding: utf-8 -*-
"""BeeAgent defaults for Hub-managed personal runtimes.

Every new (and under-provisioned) runtime should get:
  - DeepSeek provider + active model ``deepseek-flash``
  - ``web_search`` / ``web_fetch`` enabled with DeepSeek as search provider
  - BeeAgent official Skills (专项) when the pack is available on disk

Requires ``DEEPSEEK_API_KEY`` in the Hub process environment
(``local/secrets/deepseek.env`` via ``manage.sh``).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER_ID = "deepseek"
DEFAULT_MODEL_ID = "deepseek-flash"
BOOTSTRAP_KILO_MODELS = {
    "kilo-auto/free",
    "kilo-auto/efficient",
    "kilo-auto/balanced",
    "kilo-auto/small",
    "kilo-auto/frontier",
}


def _deepseek_api_key() -> str:
    return (os.environ.get("DEEPSEEK_API_KEY") or "").strip()


def _minimal_deepseek_provider(api_key: str) -> dict[str, Any]:
    return {
        "enabled": True,
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "api_key": api_key,
        "chat_model": "OpenAIChatModel",
        "models": [
            {
                "id": "deepseek-flash",
                "name": "DeepSeek Flash",
                "model_type": "chat",
                "supports_tool_calling": True,
                "source": "builtin",
            },
            {
                "id": "deepseek-v4-pro",
                "name": "DeepSeek V4 Pro",
                "model_type": "chat",
                "supports_tool_calling": True,
                "source": "builtin",
            },
        ],
        "extra_models": [],
        "discovered_models": [],
        "is_custom": False,
        "require_api_key": True,
        "api_key_prefix": "sk-",
        "freeze_url": False,
        "generate_kwargs": {},
        "custom_headers": {},
    }


def _template_deepseek_provider(api_key: str) -> dict[str, Any]:
    """Prefer an existing admin/runtime deepseek.json as the schema template."""
    hub_root = Path.home() / ".qwenpaw" / "hub" / "runtimes"
    if hub_root.is_dir():
        candidates = sorted(
            hub_root.glob("*/secrets/providers/builtin/deepseek.json"),
        )
        for path in candidates:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # pylint: disable=broad-exception-caught
                continue
            if not isinstance(data, dict) or data.get("id") != "deepseek":
                continue
            data = json.loads(json.dumps(data))  # deep copy
            data["api_key"] = api_key
            data["enabled"] = True
            return data
    return _minimal_deepseek_provider(api_key)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _should_set_active_model(active_path: Path) -> bool:
    if not active_path.exists():
        return True
    try:
        data = json.loads(active_path.read_text(encoding="utf-8"))
    except Exception:  # pylint: disable=broad-exception-caught
        return True
    if not isinstance(data, dict):
        return True
    provider = str(data.get("provider_id") or "")
    model = str(data.get("model") or "")
    if provider == "kilo" and model in BOOTSTRAP_KILO_MODELS:
        return True
    if not provider or not model:
        return True
    return False


def ensure_provider_secrets(secret_dir: Path) -> dict[str, Any]:
    """Write DeepSeek provider + active_model under a runtime secret dir."""
    result = {
        "provider": False,
        "active_model": False,
        "skipped": False,
        "reason": "",
    }
    api_key = _deepseek_api_key()
    if not api_key:
        result["skipped"] = True
        result["reason"] = "DEEPSEEK_API_KEY missing"
        return result

    providers_dir = Path(secret_dir) / "providers" / "builtin"
    provider_path = providers_dir / "deepseek.json"
    active_path = Path(secret_dir) / "providers" / "active_model.json"

    need_provider = True
    if provider_path.exists():
        try:
            existing = json.loads(provider_path.read_text(encoding="utf-8"))
            if (
                isinstance(existing, dict)
                and existing.get("id") == "deepseek"
                and existing.get("api_key")
                and existing.get("enabled", True)
            ):
                need_provider = False
        except Exception:  # pylint: disable=broad-exception-caught
            need_provider = True

    if need_provider:
        _write_json(provider_path, _template_deepseek_provider(api_key))
        result["provider"] = True

    if _should_set_active_model(active_path):
        _write_json(
            active_path,
            {
                "provider_id": DEFAULT_PROVIDER_ID,
                "model": DEFAULT_MODEL_ID,
            },
        )
        result["active_model"] = True

    return result


def _ensure_tool_entry(
    builtin: dict[str, Any],
    name: str,
    *,
    enabled: bool,
    provider: str | None = None,
) -> bool:
    changed = False
    entry = builtin.get(name)
    if not isinstance(entry, dict):
        entry = {
            "name": name,
            "enabled": enabled,
            "display_to_user": True,
            "async_execution": True,
            "config": {},
        }
        if name == "web_search":
            entry["description"] = "Search the web for real-time information"
            entry["icon"] = "🔎"
        elif name == "web_fetch":
            entry["description"] = "Fetch and read content from a URL"
            entry["icon"] = "📥"
        builtin[name] = entry
        changed = True
    if entry.get("enabled") != enabled:
        entry["enabled"] = enabled
        changed = True
    if provider:
        config = entry.setdefault("config", {})
        if not isinstance(config, dict):
            config = {}
            entry["config"] = config
        if config.get("provider") != provider:
            config["provider"] = provider
            changed = True
    return changed


def ensure_tool_defaults(
    working_dir: Path,
    *,
    enable_web_search: bool = True,
    enable_web_fetch: bool = True,
) -> int:
    """Ensure web_search/web_fetch exist and use DeepSeek where applicable."""
    changed = 0
    working = Path(working_dir)
    targets: list[Path] = []
    config_path = working / "config.json"
    if config_path.exists():
        targets.append(config_path)
    default_agent = working / "workspaces" / "default" / "agent.json"
    if default_agent.exists():
        targets.append(default_agent)

    for path in targets:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # pylint: disable=broad-exception-caught
            continue
        if not isinstance(data, dict):
            continue
        tools = data.setdefault("tools", {})
        if not isinstance(tools, dict):
            continue
        builtin = tools.setdefault("builtin_tools", {})
        if not isinstance(builtin, dict):
            continue
        local = 0
        if _ensure_tool_entry(
            builtin,
            "web_search",
            enabled=enable_web_search,
            provider="deepseek",
        ):
            local += 1
        if _ensure_tool_entry(
            builtin,
            "web_fetch",
            enabled=enable_web_fetch,
            provider=None,
        ):
            local += 1
        if local:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            changed += local
    return changed


def _beeagent_root() -> Path | None:
    """Locate the BeeAgent repo that ships ``local/official_skills``."""
    env = (os.environ.get("BEEAGENT_ROOT") or "").strip()
    if env:
        candidate = Path(env).expanduser()
        if (candidate / "local" / "official_skills").is_dir():
            return candidate
    # hub/beeagent_defaults.py → qwenpaw → src → QwenPaw → BeeAgent
    candidate = Path(__file__).resolve().parents[4]
    if (candidate / "local" / "official_skills").is_dir():
        return candidate
    return None


# Keep in sync with qwenpaw.hub.rbac.catalog.OFFICIAL_SKILLS (avoid importing
# rbac package here — its __init__ pulls FastAPI).
_OFFICIAL_SKILL_NAMES: tuple[str, ...] = (
    "koujing-xiezhuan",
    "wangping-huashu",
    "shensu-chegao",
    "yuqing-yanpan",
    "yuan-xiezhuan",
    "shiqian-pinggu",
    "paicha-fangan",
    "weike-wenan",
    "yanlian-jiaoben",
    "shuju-chuli",
    "yuqing-baogao",
)


def _official_skills_already_enabled(working: Path) -> bool:
    """True when the nine BeeAgent official skills are already on the workspace."""
    skill_json = working / "workspaces" / "default" / "skill.json"
    if not skill_json.exists():
        return False
    try:
        data = json.loads(skill_json.read_text(encoding="utf-8"))
    except Exception:  # pylint: disable=broad-exception-caught
        return False
    skills = data.get("skills") if isinstance(data, dict) else None
    if not isinstance(skills, dict):
        return False
    for name in _OFFICIAL_SKILL_NAMES:
        entry = skills.get(name)
        if not isinstance(entry, dict) or not entry.get("enabled"):
            return False
        if not (
            working / "workspaces" / "default" / "skills" / name / "SKILL.md"
        ).exists():
            return False
    return True


def ensure_official_skills(working_dir: Path) -> int:
    """Install official BeeAgent Skills into one runtime (idempotent).

    No-op when the default workspace is not ready yet (pre-first-boot) or the
    skills pack / sync script cannot be found. Prefers ``BEEAGENT_ROOT``.

    Re-entrancy: ``sync_official_skills.py`` itself calls
    ``ensure_runtime_defaults``; skip spawning another sync in that case.
    """
    if os.environ.get("BEEAGENT_SKILL_SYNC") == "1":
        return 0
    working = Path(working_dir)
    if not (working / "workspaces" / "default").exists():
        return 0
    if _official_skills_already_enabled(working):
        return 0
    root = _beeagent_root()
    if root is None:
        logger.warning(
            "BeeAgent official skills pack not found; skip skill sync for %s",
            working,
        )
        return 0
    script = root / "local" / "scripts" / "sync_official_skills.py"
    if not script.is_file():
        logger.warning("missing sync_official_skills.py under %s", root)
        return 0
    env = os.environ.copy()
    env["BEEAGENT_SKILL_SYNC"] = "1"
    env.setdefault("BEEAGENT_ROOT", str(root))
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--runtime", str(working)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            cwd=str(root),
            env=env,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning(
            "official skills sync failed for %s",
            working,
            exc_info=True,
        )
        return 0
    if proc.returncode != 0:
        logger.warning(
            "official skills sync exit=%s for %s: %s",
            proc.returncode,
            working,
            (proc.stderr or proc.stdout or "").strip()[-500:],
        )
        return 0
    logger.info("official skills synced for %s", working.name)
    return 1


def ensure_runtime_defaults(
    secret_dir: Path,
    working_dir: Path | None = None,
) -> dict[str, Any]:
    """Apply BeeAgent DeepSeek defaults + official Skills to one runtime."""
    secret_result = ensure_provider_secrets(secret_dir)
    tool_changes = 0
    skill_sync = 0
    if working_dir is not None:
        tool_changes = ensure_tool_defaults(working_dir)
        skill_sync = ensure_official_skills(working_dir)
    return {
        **secret_result,
        "tool_changes": tool_changes,
        "skill_sync": skill_sync,
    }


def inject_deepseek_env(environment: dict[str, str]) -> None:
    """Pass Hub DeepSeek key into the child runtime process env."""
    api_key = _deepseek_api_key()
    if api_key:
        environment["DEEPSEEK_API_KEY"] = api_key
