#!/usr/bin/env bash
# Copy Huiyin brand static assets into QwenPaw console/public.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BRAND="$ROOT/local/brand/huiyin/images"
PUBLIC="$ROOT/QwenPaw/console/public"

[[ -d "$BRAND" ]] || { echo "missing $BRAND"; exit 1; }
[[ -d "$PUBLIC" ]] || { echo "missing $PUBLIC"; exit 1; }

cp "$BRAND/logo.png" "$PUBLIC/qwenpaw.png"
cp "$BRAND/logo-mark.png" "$PUBLIC/brand-logo.png"
cp "$BRAND/login/hy-logo-white.png" "$PUBLIC/brand-logo-dark.png"
cp "$BRAND/icon.png" "$PUBLIC/brand-icon.png"
cp "$BRAND/favicon.ico" "$PUBLIC/favicon.ico"
# Keep svg filenames but point UI code at PNG brand files; leave old svgs as unused fallbacks.
cp "$BRAND/logo.png" "$PUBLIC/logo-light.png"
cp "$BRAND/login/hy-logo-white.png" "$PUBLIC/logo-dark.png"
mkdir -p "$PUBLIC/brand/login"
cp "$BRAND/login/bg.svg" "$PUBLIC/brand/login/bg.svg"
cp "$BRAND/login/bg.png" "$PUBLIC/brand/login/bg.png"
cp -r "$BRAND/login/icons" "$PUBLIC/brand/login/" 2>/dev/null || true

echo "Huiyin brand assets applied to $PUBLIC"
