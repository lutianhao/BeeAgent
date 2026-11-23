#!/usr/bin/env python3
"""Shared helpers for Volcengine Ark (方舟) media scripts."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
LOCAL_DIR = SCRIPT_DIR.parent.parent
ROOT_DIR = LOCAL_DIR.parent
SECRETS_DIR = LOCAL_DIR / "secrets"
DEFAULT_OUT_DIR = LOCAL_DIR / "run" / "volcengine"
DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_SEEDREAM_MODEL = "doubao-seedream-5-5-261028"
DEFAULT_SEEDANCE_MODEL = "doubao-seedance-2-0-260128"


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def load_ark_env() -> None:
    """Load local/secrets/ark.env then optional overrides; never print secrets."""
    _load_env_file(SECRETS_DIR / "ark.env")
    # Allow a shared volcengine.env alias if present
    _load_env_file(SECRETS_DIR / "volcengine.env")


def require_api_key() -> str:
    load_ark_env()
    key = (
        os.environ.get("ARK_API_KEY")
        or os.environ.get("VOLCENGINE_API_KEY")
        or os.environ.get("VOLC_ARK_API_KEY")
        or ""
    ).strip()
    if not key:
        example = SECRETS_DIR / "ark.env.example"
        raise SystemExit(
            "缺少 ARK_API_KEY。请先创建 local/secrets/ark.env（可参考 "
            f"{example.relative_to(ROOT_DIR)}），或 export ARK_API_KEY=..."
        )
    return key


def base_url() -> str:
    load_ark_env()
    return (
        os.environ.get("ARK_BASE_URL") or DEFAULT_BASE_URL
    ).rstrip("/")


def seedream_model() -> str:
    load_ark_env()
    return os.environ.get("ARK_SEEDREAM_MODEL") or DEFAULT_SEEDREAM_MODEL


def seedance_model() -> str:
    load_ark_env()
    return os.environ.get("ARK_SEEDANCE_MODEL") or DEFAULT_SEEDANCE_MODEL


def ensure_out_dir(path: Path | None = None) -> Path:
    out = path or DEFAULT_OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    return out


def http_json(
    method: str,
    url: str,
    *,
    api_key: str,
    body: dict[str, Any] | None = None,
    timeout: float = 180.0,
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method.upper(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} {url}\n{detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"请求失败: {exc}") from exc


def download(url: str, dest: Path, *, timeout: float = 180.0) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "BeeAgent-ark-scripts/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, dest.open("wb") as fh:
        fh.write(resp.read())
    return dest


def file_to_data_url(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    if not mime or not mime.startswith("image/"):
        # Ark expects lowercase image/* ; default png
        suffix = path.suffix.lower().lstrip(".") or "png"
        if suffix == "jpg":
            suffix = "jpeg"
        mime = f"image/{suffix}"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)
