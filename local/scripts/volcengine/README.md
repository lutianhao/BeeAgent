# 火山方舟（Ark）媒体脚本

给 BeeAgent 本地用的 **Seedream 生图** / **Seedance 生视频** CLI。Key 放 `local/secrets/`，产物默认落到 `local/run/volcengine/`。

## 1. 配置 Key

```bash
cp local/scripts/volcengine/ark.env.example local/secrets/ark.env
# 编辑 ark.env，填入 ARK_API_KEY=...
```

也可临时：

```bash
export ARK_API_KEY=你的key
```

`local/secrets/ark.env` 已被 gitignore，不会进仓库。

## 2. 生图（Seedream）

```bash
# 文生图
python local/scripts/volcengine/seedream_image.py \
  --prompt "蓝色盾牌里的橙色小蜜蜂，扁平科技风 logo，纯黑背景" \
  --size 2K \
  --out local/run/volcengine/bee-mark.png

# 图生图（升级现有品牌标）
python local/scripts/volcengine/seedream_image.py \
  --prompt "升级这枚品牌标：更清晰的扁平矢量，保留橙色蜜蜂+蓝盾+电路节点，纯黑方底，不要文字" \
  --image local/brand/huiyin/images/icon.png \
  --size 2K \
  --out local/run/volcengine/bee-mark-upgraded.png
```

常用参数：`--model` / `--size` / `--watermark` / `--no-watermark` / `--dry-run`

## 3. 生视频（Seedance）

异步任务：创建 → 轮询 → 下载 mp4。

```bash
# 文生视频
python local/scripts/volcengine/seedance_video.py \
  --prompt "蓝色盾牌上的橙色小蜜蜂轻微扇动翅膀，电路节点柔和闪烁，黑底，适合循环头像" \
  --ratio 1:1 --duration 5 \
  --out local/run/volcengine/bee-avatar.mp4

# 图生视频（首帧）
python local/scripts/volcengine/seedance_video.py \
  --prompt "蜜蜂翅膀轻微扇动，电路光点缓慢呼吸，镜头固定" \
  --image local/brand/huiyin/images/icon.png \
  --role first_frame \
  --ratio 1:1 --duration 5
```

只下载已有任务：

```bash
python local/scripts/volcengine/seedance_video.py --task-id cgt-xxxx --out local/run/volcengine/out.mp4
```

## 4. 模型说明

| 用途 | 脚本 | 默认模型环境变量 | 默认 Model ID |
|------|------|------------------|---------------|
| 静图 / 图编辑 | `seedream_image.py` | `ARK_SEEDREAM_MODEL` | `doubao-seedream-5-5-261028` |
| 短视频 | `seedance_video.py` | `ARK_SEEDANCE_MODEL` | `doubao-seedance-2-0-260128` |

若控制台开通的是 **推理接入点 Endpoint ID**，把 `--model` 或环境变量改成该 ID 即可。

品牌升级建议流程：**Seedream 图生图**出静帧 → 需要动效再用 **Seedance 图生视频** → 本地转 GIF（如需）。

## 5. 依赖

仅 Python 标准库（`urllib`）。建议在 `qwenpaw` conda 环境执行。
