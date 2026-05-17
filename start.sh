#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Optional settings. Copy env.example to .env and edit if you want.
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

export PORT="${PORT:-8787}"
export TZ_NAME="${TZ_NAME:-Europe/Istanbul}"
export REFRESH_SECONDS="${REFRESH_SECONDS:-30}"
export OPENCLAW_BIN="${OPENCLAW_BIN:-openclaw}"

python3 server.py
