#!/usr/bin/env bash
set -euo pipefail

# TEMPLATE — not auto-loaded. See docs/cloudflare-tradingview-setup.md
# before deploying. This wrapper assumes:
#   - cloudflared is installed (brew install cloudflared)
#   - the tunnel `tradenest-webhook` already exists and its credentials
#     live under ~/.cloudflared/ (created by `cloudflared tunnel
#     create` or by the dashboard install command)
#   - DNS is routed to the tunnel for tradenest-webhook.<your-domain>
#
# We intentionally do NOT source .env here — cloudflared has no need
# for TradeNest secrets, and credentials/config live in ~/.cloudflared/.

cd "$HOME/tradenest-runtime"

CLOUDFLARED_BIN="${CLOUDFLARED_BIN:-$(command -v cloudflared || true)}"
if [ -z "$CLOUDFLARED_BIN" ]; then
  echo "FATAL: cloudflared not found in PATH" >&2
  exit 1
fi

if [ ! -d "$HOME/.cloudflared" ]; then
  echo "FATAL: ~/.cloudflared missing — run 'cloudflared tunnel login' or follow the dashboard install command first" >&2
  exit 1
fi

printf '[%s] starting cloudflared tunnel tradenest-webhook (cwd=%s, bin=%s)\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(pwd)" "$CLOUDFLARED_BIN"

# exec so launchd tracks the real cloudflared PID rather than this wrapper.
exec "$CLOUDFLARED_BIN" tunnel run tradenest-webhook
