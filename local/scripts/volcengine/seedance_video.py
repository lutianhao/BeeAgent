#!/usr/bin/env python3
"""Volcengine Ark Seedance — 文生视频 / 图生视频（异步任务 + 轮询下载）.

用法示例：
  # 文生视频
  python local/scripts/volcengine/seedance_video.py \\
    --prompt "蓝色盾牌上的橙色小蜜蜂轻轻扇动翅膀，科技感光效，黑底" \\
    --ratio 1:1 --duration 5 \\
    --out local/run/volcengine/bee-loop.mp4

  # 图生视频（首帧）
  python local/scripts/volcengine/seedance_video.py \\
    --prompt "蜜蜂翅膀轻微扇动，电路节点柔和闪烁，循环感短镜头" \\
    --image local/brand/huiyin/images/icon.png \\
    --role first_frame --ratio 1:1 --duration 5

密钥：local/secrets/ark.env 中的 ARK_API_KEY
"""

from __future__ import annotations

import argparse
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
    seedance_model,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ark Seedance 视频生成")
    p.add_argument("--prompt", default="", help="文本提示词（可与参考图一起用）")
    p.add_argument(
        "--image",
        action="append",
        default=[],
        help="参考图路径或 URL，可重复；配合 --role",
    )
    p.add_argument(
        "--role",
        default="first_frame",
        choices=("first_frame", "last_frame", "reference_image"),
        help="参考图角色（多图时统一角色；首尾帧请传两张并分别指定见 --image-role）",
    )
    p.add_argument(
        "--image-role",
        action="append",
        default=[],
        metavar="ROLE",
        help="与每个 --image 一一对应的 role；不传则全部用 --role",
    )
    p.add_argument("--model", default=None, help="模型 ID")
    p.add_argument("--resolution", default="720p", help="如 480p/720p/1080p")
    p.add_argument("--ratio", default="16:9", help="如 16:9 / 1:1 / 9:16")
    p.add_argument("--duration", type=int, default=5, help="秒数（视模型而定）")
    p.add_argument("--seed", type=int, default=None, help="随机种子")
    p.add_argument(
        "--watermark",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="是否加水印（默认不加）",
    )
    p.add_argument(
        "--camera-fixed",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="是否固定镜头",
    )
    p.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="轮询间隔秒",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=900.0,
        help="最长等待秒",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="保存路径（默认 local/run/volcengine/seedance-<ts>.mp4）",
    )
    p.add_argument(
        "--task-id",
        default=None,
        help="只查询并下载已有任务（跳过创建）",
    )
    p.add_argument("--dry-run", action="store_true", help="只打印创建请求体")
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


def build_content(args: argparse.Namespace) -> list[dict]:
    content: list[dict] = []
    if args.prompt.strip():
        content.append({"type": "text", "text": args.prompt.strip()})
    roles = args.image_role or []
    if roles and len(roles) != len(args.image):
        raise SystemExit("--image-role 数量必须与 --image 一致")
    for i, ref in enumerate(args.image):
        role = roles[i] if roles else args.role
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": resolve_image_ref(ref)},
                "role": role,
            }
        )
    if not content:
        raise SystemExit("至少提供 --prompt 或 --image")
    return content


def create_task(api_key: str, body: dict) -> str:
    url = f"{base_url()}/contents/generations/tasks"
    resp = http_json("POST", url, api_key=api_key, body=body, timeout=120.0)
    task_id = resp.get("id")
    if not task_id:
        raise SystemExit(f"创建任务失败: {resp}")
    return str(task_id)


def get_task(api_key: str, task_id: str) -> dict:
    url = f"{base_url()}/contents/generations/tasks/{task_id}"
    return http_json("GET", url, api_key=api_key, timeout=60.0)


def wait_task(
    api_key: str,
    task_id: str,
    *,
    interval: float,
    timeout: float,
) -> dict:
    deadline = time.time() + timeout
    while True:
        info = get_task(api_key, task_id)
        status = info.get("status")
        eprint(f"[{task_id}] status={status}")
        if status == "succeeded":
            return info
        if status in {"failed", "cancelled", "expired"}:
            raise SystemExit(f"任务结束: {status}\n{info}")
        if time.time() >= deadline:
            raise SystemExit(f"等待超时（{timeout}s），task_id={task_id}")
        time.sleep(interval)


def main() -> int:
    args = parse_args()
    model = args.model or seedance_model()

    if args.task_id:
        api_key = require_api_key()
        info = wait_task(
            api_key,
            args.task_id,
            interval=args.poll_interval,
            timeout=args.timeout,
        )
    else:
        body: dict = {
            "model": model,
            "content": build_content(args),
            "resolution": args.resolution,
            "ratio": args.ratio,
            "duration": args.duration,
            "watermark": bool(args.watermark),
        }
        if args.seed is not None:
            body["seed"] = args.seed
        if args.camera_fixed is not None:
            body["camera_fixed"] = bool(args.camera_fixed)

        if args.dry_run:
            preview = dict(body)
            preview_content = []
            for item in preview["content"]:
                if item.get("type") == "image_url":
                    url = item.get("image_url", {}).get("url", "")
                    preview_content.append(
                        {
                            **item,
                            "image_url": {
                                "url": (
                                    url[:48] + "...(omitted)"
                                    if url.startswith("data:")
                                    else url
                                )
                            },
                        }
                    )
                else:
                    preview_content.append(item)
            preview["content"] = preview_content
            print(preview)
            return 0

        api_key = require_api_key()
        eprint(f"Seedance → {model}")
        task_id = create_task(api_key, body)
        eprint(f"created task_id={task_id}")
        info = wait_task(
            api_key,
            task_id,
            interval=args.poll_interval,
            timeout=args.timeout,
        )

    video_url = (info.get("content") or {}).get("video_url")
    if not video_url:
        raise SystemExit(f"成功但无 video_url: {info}")

    out_dir = ensure_out_dir()
    ts = time.strftime("%Y%m%d-%H%M%S")
    out = args.out or (out_dir / f"seedance-{ts}.mp4")
    if not out.is_absolute():
        out = (ROOT_DIR / out).resolve()
    download(video_url, out, timeout=300.0)
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
