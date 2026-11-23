#!/usr/bin/env bash
# Free TCP 8094 (dead nginx→8501 vhost) and restart QwenPaw Hub on 8094.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
NGINX_CONF="/etc/nginx/conf.d/gangjin.conf"

echo "[1/3] Free port 8094 (needs sudo)…"
if ss -tln | grep -q ':8094'; then
  if [[ -f "$NGINX_CONF" ]]; then
    sudo cp -a "$NGINX_CONF" "${NGINX_CONF}.bak.$(date +%Y%m%d%H%M%S)"
    sudo mv "$NGINX_CONF" "${NGINX_CONF}.disabled"
    sudo nginx -t
    sudo systemctl reload nginx
    echo "  disabled $NGINX_CONF and reloaded nginx"
  else
    echo "  8094 is in use but $NGINX_CONF is missing; free the port manually then re-run."
    ss -tlnp | grep ':8094' || true
    exit 1
  fi
else
  echo "  8094 already free"
fi

echo "[2/3] Ensure hub.env points at 8094…"
mkdir -p "$ROOT/local/secrets"
cat >"$ROOT/local/secrets/hub.env" <<'EOF'
HUB_HOST=0.0.0.0
HUB_PORT=8094
EOF

echo "[3/3] Restart Hub on 8094…"
"$ROOT/local/scripts/manage.sh" restart
"$ROOT/local/scripts/manage.sh" status

echo
curl -s -o /dev/null -w "check http://127.0.0.1:8094/ -> %{http_code}\n" http://127.0.0.1:8094/ || true
echo "Done. Open http://192.168.3.67:8094/"
