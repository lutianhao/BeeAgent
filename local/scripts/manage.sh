#!/usr/bin/env bash
# BeeAgent / QwenPaw Hub 统一管理脚本（宿主机 conda 进程）
#
# 用法（在任意目录执行均可）：
#   ./local/scripts/manage.sh start
#   ./local/scripts/manage.sh stop
#   ./local/scripts/manage.sh restart
#   ./local/scripts/manage.sh status
#   ./local/scripts/manage.sh logs [-f]
#
# 支持两种目录布局：
#   1) 仓库内：<repo>/local  + <repo>/src/qwenpaw   （推荐，clone 即用）
#   2) 兄弟目录：BeeAgent/local + BeeAgent/QwenPaw
#
# 依赖：
#   - conda 环境：qwenpaw
#   - 密钥：local/secrets/*.env（从 *.example 复制）

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# -P：解析软链，避免 BeeAgent/local -> repo/local 时路径算错
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
LOCAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
PARENT_DIR="$(cd "$LOCAL_DIR/.." && pwd -P)"

if [[ -d "$PARENT_DIR/src/qwenpaw" || -f "$PARENT_DIR/pyproject.toml" ]]; then
  # local/ 在源码仓库内
  ROOT_DIR="$PARENT_DIR"
  QWENPAW_DIR="${QWENPAW_DIR:-$PARENT_DIR}"
else
  # 旧布局：local 与 QwenPaw 并列
  ROOT_DIR="$PARENT_DIR"
  QWENPAW_DIR="${QWENPAW_DIR:-$ROOT_DIR/QwenPaw}"
fi

CONDA_ENV="${CONDA_ENV:-qwenpaw}"

HUB_HOST="${HUB_HOST:-0.0.0.0}"
HUB_PORT="${HUB_PORT:-8100}"
HUB_CONFIG="${HUB_CONFIG:-$QWENPAW_DIR/hub.yaml}"
FORCE_PUBLIC="${FORCE_PUBLIC:-1}"

RUN_DIR="${RUN_DIR:-$LOCAL_DIR/run}"
LOG_DIR="${LOG_DIR:-$RUN_DIR/logs}"
PID_FILE="${PID_FILE:-$RUN_DIR/qwenpaw-hub.pid}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/qwenpaw-hub.log}"
SECRETS_DIR="${SECRETS_DIR:-$LOCAL_DIR/secrets}"

mkdir -p "$RUN_DIR" "$LOG_DIR"

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERR]${NC} $*" >&2; }

load_secrets() {
  # Hub / sync scripts resolve official skills via BEEAGENT_ROOT/local/...
  export BEEAGENT_ROOT="${BEEAGENT_ROOT:-$ROOT_DIR}"
  # Optional Hub bind overrides (e.g. HUB_PORT=8094).
  if [[ -f "$SECRETS_DIR/hub.env" ]]; then
    # shellcheck disable=SC1090
    set -a
    source "$SECRETS_DIR/hub.env"
    set +a
  fi
  if [[ -f "$SECRETS_DIR/deepseek.env" ]]; then
    # shellcheck disable=SC1090
    set -a
    source "$SECRETS_DIR/deepseek.env"
    set +a
  fi
  if [[ -f "$SECRETS_DIR/ark.env" ]]; then
    # shellcheck disable=SC1090
    set -a
    source "$SECRETS_DIR/ark.env"
    set +a
  fi
}

conda_ready() {
  if ! command -v conda >/dev/null 2>&1; then
    err "未找到 conda，请先安装 Miniconda/Anaconda"
    exit 1
  fi
  # shellcheck disable=SC1091
  source "$(conda info --base)/etc/profile.d/conda.sh"
  if ! conda env list | awk '{print $1}' | grep -qx "$CONDA_ENV"; then
    err "conda 环境不存在: $CONDA_ENV"
    exit 1
  fi
  conda activate "$CONDA_ENV"
}

hub_pid_from_file() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "$pid"
      return 0
    fi
  fi
  return 1
}

hub_pids_by_port() {
  ss -tlnp 2>/dev/null | awk -v p=":$HUB_PORT" '
    index($4, p) {
      if (match($0, /pid=[0-9]+/)) {
        pid=substr($0, RSTART+4, RLENGTH-4)
        print pid
      }
    }' | sort -u
}

is_running() {
  hub_pid_from_file >/dev/null && return 0
  [[ -n "$(hub_pids_by_port)" ]] && return 0
  return 1
}

health_check() {
  # /api/hub/healthz 需要登录；用公开接口判断控制面是否起来
  curl -fsS --max-time 3 "http://127.0.0.1:${HUB_PORT}/api/auth/status" >/dev/null 2>&1 \
    || curl -fsS --max-time 3 "http://127.0.0.1:${HUB_PORT}/" >/dev/null 2>&1
}

show_help() {
  cat << EOF
╔════════════════════════════════════════════════════════════╗
║     BeeAgent / QwenPaw Hub 管理（manage.sh）                ║
╚════════════════════════════════════════════════════════════╝

用法: $0 <命令> [选项]

命令:
  start              启动 QwenPaw Hub（${HUB_HOST}:${HUB_PORT}）
  stop               停止 Hub
  restart            重启 Hub
  status             查看运行状态与健康检查
  logs [-f]          查看日志（-f 跟踪）
  sync-skills [--force]  同步官方 Skills 到全部 Hub 用户运行时（推荐）
  provision-defaults 为全部运行时注入 DeepSeek 模型 + web_search/web_fetch
  sync-agents [--force]  （兼容）旧版专家智能体同步；现已改为 Skills
  doctor             检查 conda / 配置 / 端口 / bwrap
  help               显示帮助

环境变量（可选覆盖）:
  CONDA_ENV          默认 qwenpaw
  HUB_HOST           默认 0.0.0.0
  HUB_PORT           默认 8100
  HUB_CONFIG         默认 \$QWENPAW_DIR/hub.yaml
  FORCE_PUBLIC       默认 1（监听非本机时需要）
  QWENPAW_DIR        默认 \$ROOT/QwenPaw

密钥文件:
  $SECRETS_DIR/deepseek.env   # DEEPSEEK_API_KEY=...
  $SECRETS_DIR/hub-admin.txt  # 管理员账号信息

示例:
  $0 start
  $0 status
  $0 logs -f
  $0 restart
  $0 sync-skills --force
EOF
}

do_provision_defaults() {
  local script="$SCRIPT_DIR/provision_runtime_defaults.py"
  [[ -f "$script" ]] || { err "缺少 $script"; exit 1; }
  load_secrets
  info "为全部 Hub 运行时注入 DeepSeek 默认模型/工具"
  python3 "$script"
  ok "DeepSeek 默认配置已同步"
}

do_sync_skills() {
  local force=0
  if [[ "${1:-}" == "--force" || "${1:-}" == "-f" ]]; then
    force=1
  fi
  local script="$SCRIPT_DIR/sync_official_skills.py"
  [[ -f "$script" ]] || { err "缺少 $script"; exit 1; }
  load_secrets
  info "同步官方 Skills: $ROOT_DIR/local/official_skills"
  if [[ "$force" -eq 1 ]]; then
    python3 "$script" --force
  else
    python3 "$script"
  fi
  ok "官方 Skills 已同步；专家 Agent 已停用，默认保持通用智能体"
}

do_sync_agents() {
  # Backward-compatible alias: experts are now Skills on the general agent.
  warn "sync-agents 已弃用，改为 sync-skills（专家能力以 Skill 安装到通用智能体）"
  do_sync_skills "$@"
}

do_doctor() {
  info "ROOT_DIR=$ROOT_DIR"
  info "QWENPAW_DIR=$QWENPAW_DIR"
  info "CONDA_ENV=$CONDA_ENV"
  info "HUB=${HUB_HOST}:${HUB_PORT}"
  info "CONFIG=$HUB_CONFIG"

  [[ -d "$QWENPAW_DIR" ]] && ok "QwenPaw 目录存在" || err "缺少 QwenPaw 目录"
  [[ -f "$HUB_CONFIG" ]] && ok "hub.yaml 存在" || warn "缺少 hub.yaml（将使用默认配置）"
  [[ -f "$SECRETS_DIR/deepseek.env" ]] && ok "deepseek.env 存在" || warn "缺少 deepseek.env"
  [[ -f "$SECRETS_DIR/hub-admin.txt" ]] && ok "hub-admin.txt 存在" || warn "缺少 hub-admin.txt"

  conda_ready
  ok "conda 环境可激活: $CONDA_ENV"
  command -v qwenpaw >/dev/null && ok "qwenpaw CLI: $(command -v qwenpaw)" || err "qwenpaw CLI 不可用"

  if command -v bwrap >/dev/null 2>&1; then
    if bwrap --ro-bind / / --proc /proc --dev /dev --unshare-user --uid 0 --gid 0 true 2>/dev/null; then
      ok "bwrap 可用（Local 隔离）"
    else
      warn "bwrap 存在但 UID map 失败；检查 kernel.apparmor_restrict_unprivileged_userns"
    fi
  else
    warn "未安装 bwrap"
  fi

  if is_running; then
    ok "Hub 进程在运行"
    health_check && ok "healthz 正常" || warn "healthz 未通过"
  else
    warn "Hub 未运行"
  fi
}

do_start() {
  if is_running; then
    warn "Hub 已在运行"
    do_status
    return 0
  fi

  [[ -d "$QWENPAW_DIR" ]] || { err "找不到 QwenPaw: $QWENPAW_DIR"; exit 1; }
  conda_ready
  load_secrets

  # Hub 控制面使用默认 ~/.qwenpaw；清掉租户 runtime 残留环境，避免找错管理员库
  unset QWENPAW_WORKING_DIR QWENPAW_SECRET_DIR QWENPAW_BACKUP_DIR QWENPAW_RUNTIME_ID || true

  if [[ ! -f "$HUB_CONFIG" ]]; then
    warn "未找到 $HUB_CONFIG，将不传 --config"
  fi

  local cmd=(qwenpaw hub --host "$HUB_HOST" --port "$HUB_PORT" --log-level info)
  if [[ -f "$HUB_CONFIG" ]]; then
    cmd+=(--config "$HUB_CONFIG")
  fi
  if [[ "$FORCE_PUBLIC" == "1" && "$HUB_HOST" != "127.0.0.1" && "$HUB_HOST" != "localhost" ]]; then
    cmd+=(--force-public)
  fi

  info "启动: ${cmd[*]}"
  info "日志: $LOG_FILE"
  (
    cd "$QWENPAW_DIR"
    unset QWENPAW_WORKING_DIR QWENPAW_SECRET_DIR QWENPAW_BACKUP_DIR QWENPAW_RUNTIME_ID || true
    nohup "${cmd[@]}" >>"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
  )

  local i
  for i in $(seq 1 40); do
    if health_check; then
      ok "Hub 已启动: http://${HUB_HOST}:${HUB_PORT}/  (本机 http://127.0.0.1:${HUB_PORT}/)"
      # 启动后把官方 Skills 注入所有租户运行时，并停用旧专家 Agent
      do_sync_skills || warn "官方 Skills 同步失败（可稍后执行: $0 sync-skills）"
      do_status
      return 0
    fi
    sleep 0.5
  done

  err "启动超时，请查看日志: $0 logs"
  exit 1
}

do_stop() {
  local stopped=0
  local pid
  if pid="$(hub_pid_from_file)"; then
    info "停止 PID $pid"
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.25
    done
    if kill -0 "$pid" 2>/dev/null; then
      warn "优雅停止超时，强制结束 $pid"
      kill -9 "$pid" 2>/dev/null || true
    fi
    stopped=1
  fi

  local p
  for p in $(hub_pids_by_port); do
    info "停止占用 ${HUB_PORT} 的进程 $p"
    kill "$p" 2>/dev/null || true
    sleep 0.2
    kill -0 "$p" 2>/dev/null && kill -9 "$p" 2>/dev/null || true
    stopped=1
  done

  rm -f "$PID_FILE"
  if [[ "$stopped" -eq 1 ]]; then
    ok "Hub 已停止"
  else
    warn "Hub 本来就没在跑"
  fi
}

do_restart() {
  do_stop || true
  sleep 1
  do_start
}

do_status() {
  echo "──────── QwenPaw Hub 状态 ────────"
  echo "host/port : ${HUB_HOST}:${HUB_PORT}"
  echo "config    : ${HUB_CONFIG}"
  echo "pid file  : ${PID_FILE}"
  echo "log file  : ${LOG_FILE}"

  local pid
  if pid="$(hub_pid_from_file)"; then
    echo -e "process   : ${GREEN}running${NC} (pid=$pid)"
  elif [[ -n "$(hub_pids_by_port)" ]]; then
    echo -e "process   : ${GREEN}running${NC} (port pids=$(hub_pids_by_port | tr '\n' ' '))"
  else
    echo -e "process   : ${RED}stopped${NC}"
  fi

  if health_check; then
    local body
    body="$(curl -fsS --max-time 3 "http://127.0.0.1:${HUB_PORT}/api/auth/status" 2>/dev/null || true)"
    echo -e "health    : ${GREEN}ok${NC}"
    [[ -n "$body" ]] && echo "auth      : $body"
  else
    echo -e "health    : ${RED}unavailable${NC}"
  fi

  if [[ -f "$SECRETS_DIR/hub-admin.txt" ]]; then
    echo "admin     : $SECRETS_DIR/hub-admin.txt"
  fi
  if [[ -f "$SECRETS_DIR/deepseek.env" ]]; then
    echo "deepseek  : key file present"
  else
    echo "deepseek  : key file missing"
  fi
}

do_logs() {
  local follow=0
  if [[ "${1:-}" == "-f" || "${1:-}" == "--follow" ]]; then
    follow=1
  fi
  if [[ ! -f "$LOG_FILE" ]]; then
    warn "日志文件不存在: $LOG_FILE"
    exit 1
  fi
  if [[ "$follow" -eq 1 ]]; then
    tail -n 100 -f "$LOG_FILE"
  else
    tail -n 120 "$LOG_FILE"
  fi
}

cmd="${1:-help}"
shift || true

case "$cmd" in
  start)   do_start ;;
  stop)    do_stop ;;
  restart) do_restart ;;
  status)  do_status ;;
  logs)    do_logs "$@" ;;
  sync-skills) do_sync_skills "$@" ;;
  provision-defaults) do_provision_defaults ;;
  sync-agents) do_sync_agents "$@" ;;
  doctor)  do_doctor ;;
  help|--help|-h) show_help ;;
  *)
    err "未知命令: $cmd"
    show_help
    exit 1
    ;;
esac
