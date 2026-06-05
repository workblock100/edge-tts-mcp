#!/usr/bin/env bash
# Start the Edge TTS MCP server + cloudflared tunnel.
# Run this after a Mac restart, or anytime the server/tunnel dies.
#
# If the cloudflared URL changes, you must update:
#   1. PUBLIC_URL in .env (this script does it for you)
#   2. The custom connector URL in claude.ai → Settings → Connectors → Edge TTS
#      → must be: <new URL>/<MCP_SECRET>/mcp

set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "FAILED: no .env file. Run ./bootstrap.sh first."
  exit 1
fi

PORT=$(grep -E "^PORT=" .env | cut -d= -f2- || echo 8765)
PORT=${PORT:-8765}

echo "== killing any old edge-tts-mcp/cloudflared processes =="
# Kill anything bound to our port (case-insensitive match for Python/python)
OLD_PID=$(lsof -tiTCP:$PORT -sTCP:LISTEN 2>/dev/null | head -1)
if [ -n "$OLD_PID" ]; then
  kill -9 "$OLD_PID" 2>/dev/null || true
fi
pkill -if "edge-tts-mcp" 2>/dev/null || true
ps aux | grep -E "cloudflared tunnel.*localhost:$PORT|cloudflared tunnel --url http://localhost:$PORT" | grep -v grep | awk '{print $2}' | xargs -I{} kill {} 2>/dev/null || true
sleep 2

echo "== starting cloudflared =="
nohup cloudflared tunnel --url "http://localhost:$PORT" > /tmp/edge-tts-cf.log 2>&1 &
CF_PID=$!
echo "  cloudflared PID: $CF_PID"

URL=""
for i in $(seq 1 20); do
  sleep 1
  URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" /tmp/edge-tts-cf.log | head -1)
  if [ -n "$URL" ]; then
    break
  fi
done
if [ -z "$URL" ]; then
  echo "FAILED to get cloudflared URL. Check /tmp/edge-tts-cf.log"
  exit 1
fi
echo "  tunnel URL: $URL"

echo "== updating PUBLIC_URL in .env =="
OLD_URL=$(grep -E "^PUBLIC_URL=" .env | cut -d= -f2- || echo "")
if [ "$OLD_URL" != "$URL" ]; then
  echo "  URL changed: $OLD_URL  ->  $URL"
  echo "  ⚠️  Update the connector URL in claude.ai → Settings → Connectors."
fi
if grep -qE "^PUBLIC_URL=" .env; then
  sed -i.bak -E "s|^PUBLIC_URL=.*|PUBLIC_URL=$URL|" .env
else
  echo "PUBLIC_URL=$URL" >> .env
fi
rm -f .env.bak

echo "== starting edge-tts-mcp server =="
nohup .venv/bin/python server.py > /tmp/edge-tts-mcp.log 2>&1 &
SERVER_PID=$!
echo "  server PID: $SERVER_PID"
sleep 3

echo "== health =="
curl -s "http://localhost:$PORT/health"
echo
curl -s -m 8 "$URL/health"
echo

MCP_SECRET=$(grep -E "^MCP_SECRET=" .env | cut -d= -f2-)
echo
echo "== ready =="
echo "Tunnel:               $URL"
echo "Landing page:         $URL/"
echo "Claude connector URL: $URL/$MCP_SECRET/mcp"
echo
echo "Logs: /tmp/edge-tts-mcp.log  /tmp/edge-tts-cf.log"
