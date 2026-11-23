#!/usr/bin/env bash
# 新机器一键准备本机配置文件（不写真实密钥）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
LOCAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
REPO_DIR="$(cd "$LOCAL_DIR/.." && pwd -P)"
SECRETS_DIR="$LOCAL_DIR/secrets"

copy_if_missing() {
  local src="$1"
  local dst="$2"
  if [[ -f "$dst" ]]; then
    echo "[skip] $dst (已存在)"
    return
  fi
  if [[ ! -f "$src" ]]; then
    echo "[warn] 缺少模板: $src" >&2
    return
  fi
  cp "$src" "$dst"
  echo "[ok] 已创建 $dst"
}

mkdir -p "$SECRETS_DIR" "$LOCAL_DIR/run/logs"

copy_if_missing "$SECRETS_DIR/deepseek.env.example" "$SECRETS_DIR/deepseek.env"
copy_if_missing "$SECRETS_DIR/ark.env.example" "$SECRETS_DIR/ark.env"
copy_if_missing "$SECRETS_DIR/hub.env.example" "$SECRETS_DIR/hub.env"
copy_if_missing "$SECRETS_DIR/hub-admin.txt.example" "$SECRETS_DIR/hub-admin.txt"
copy_if_missing "$REPO_DIR/hub.yaml.example" "$REPO_DIR/hub.yaml"

cat << EOF

下一步：
  1. 编辑密钥： $SECRETS_DIR/deepseek.env 等
  2. 编辑 Hub：  $REPO_DIR/hub.yaml （public_base_url）
  3. 准备 conda 环境 qwenpaw，并在仓库根目录安装：
       cd $REPO_DIR && pip install -e ".[hub]"   # 或项目文档推荐方式
       cd console && npm ci && npm run build
       rsync -a --delete console/dist/ src/qwenpaw/console/
  4. 启动：
       ./local/scripts/manage.sh start
       ./local/scripts/manage.sh status

EOF
