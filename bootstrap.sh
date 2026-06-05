#!/usr/bin/env bash
# One-time setup: create .env with a fresh MCP_SECRET and install Python deps.
set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
  cat > .env <<EOF
# Random URL-path token. Anyone with this URL can call the TTS tool —
# rotate it if you ever post the connector URL anywhere public.
MCP_SECRET=$SECRET

# Filled in automatically by start.sh after cloudflared assigns a URL.
PUBLIC_URL=

# Server port (must match start.sh / stop.sh).
PORT=8765
EOF
  echo "wrote .env (MCP_SECRET=$SECRET)"
else
  echo ".env already exists — leaving it alone"
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
  echo "created .venv"
fi
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
echo "deps installed"

chmod +x start.sh stop.sh bootstrap.sh
echo "ready — run ./start.sh"
