#!/usr/bin/env python3
"""Volcengine Ark Seedream — 文生图 / 图生图（品牌素材、欢迎图等）.

用法示例：
  # 文生图
  python local/scripts/volcengine/seedream_image.py \\
    --prompt "蓝色盾牌里的橙色小蜜蜂，扁平科技风 logo，黑底" \\
    --size 1K --out local/run/volcengine/bee-mark.png

  # 图生图（保留现有特征升级）
  python local/scripts/volcengine/seedream_image.py \\
    --prompt "升级这枚品牌标：更清晰的扁平矢量，保留橙色蜜蜂+蓝盾+电路" \\
    --image local/brand/huiyin/images/icon.png \\
    --size 2K --out local/run/volcengine/bee-mark-upgraded.png

密钥：local/secrets/ark.env 中的 ARK_API_KEY（见本目录 ark.env.example）
"""

from __future__ import annotations

import argparse
import base64
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ark_common import (  # noqa: E402
    ROOT_DIR,
    base_url,
    download,
    eprint,
    ensure_out_dir,
    file_to_data_url,
    http_json,
    require_api_key,
    seedream_model,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ark Seedream 图片生成")
    p.add_argument("--prompt", required=True, help="生成/编辑提示词")
    p.add_argument(
        "--image",
        action="append",
        default=[],
        help="参考图路径或 URL，可重复传入（图生图）",
    )
    p.add_argument(
        "--model",
        default=None,
        help="模型 ID（默认 ARK_SEEDREAM_MODEL 或内置 Seedream 默认）",
    )
    p.add_argument(
        "--size",
        default="2K",
        help="尺寸：1K/2K/4K 或如 1024x1024（视模型而定）",
    )
    p.add_argument(
        "--output-format",
        default="png",
        choices=("png", "jpeg"),
        help="输出格式",
    )
    p.add_argument(
        "--response-format",
        default="url",
        choices=("url", "b64_json"),
        help="接口返回方式",
    )
    p.add_argument(
        "--watermark",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="是否加水印（默认不加）",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="保存路径（默认 local/run/volcengine/seedream-<ts>.png）",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要发送的请求体，不真正调用",
    )
    return p.parse_args()


def resolve_image_ref(ref: str) -> str:
    if ref.startswith(("http://", "https://", "data:")):
        return ref
    path = Path(ref).expanduser()
    if not path.is_file():
        path = (ROOT_DIR / ref).resolve()
    if not path.is_file():
        raise SystemExit(f"参考图不存在: {ref}")
    return file_to_data_url(path)


def _omit_data_urls(value: object) -> object:
    if isinstance(value, str) and value.startswith("data:"):
        return value[:48] + "...(base64 omitted)"
    if isinstance(value, list):
        return [_omit_data_urls(x) for x in value]
    return value


def main() -> int:
    args = parse_args()
    model = args.model or seedream_model()

    images: list[str] | str | None = None
    if args.image:
        resolved = [resolve_image_ref(x) for x in args.image]
        images = resolved[0] if len(resolved) == 1 else resolved

    body: dict = {
        "model": model,
        "prompt": args.prompt,
        "size": args.size,
        "output_format": args.output_format,
        "response_format": args.response_format,
        "watermark": bool(args.watermark),
    }
    if images is not None:
        body["image"] = images

    if args.dry_run:
        preview = {**body, "image": _omit_data_urls(body.get("image"))}
        print(preview)
        return 0

    api_key = require_api_key()
    url = f"{base_url()}/images/generations"
    eprint(f"Seedream → {model}")
    resp = http_json("POST", url, api_key=api_key, body=body, timeout=300.0)

    data = resp.get("data") or []
    if not data:
        raise SystemExit(f"响应无图片数据: {resp}")

    out_dir = ensure_out_dir()
    ts = time.strftime("%Y%m%d-%H%M%S")
    suffix = "jpg" if args.output_format == "jpeg" else "png"
    out = args.out or (out_dir / f"seedream-{ts}.{suffix}")
    if not out.is_absolute():
        out = (ROOT_DIR / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    saved: list[Path] = []
    for i, item in enumerate(data, start=1):
        target = out if i == 1 else out.with_name(f"{out.stem}-{i}{out.suffix}")
        if args.response_format == "url":
            img_url = item.get("url")
            if not img_url:
                raise SystemExit(f"缺少 url 字段: {item}")
            download(img_url, target)
        else:
            b64 = item.get("b64_json")
            if not b64:
                raise SystemExit(f"缺少 b64_json 字段: {item}")
            target.write_bytes(base64.b64decode(b64))
        saved.append(target)

    for path in saved:
        print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
