#!/usr/bin/env bash
# Stop the Edge TTS MCP server and its cloudflared tunnel.
set -e
cd "$(dirname "$0")"

PORT=$(grep -E "^PORT=" .env 2>/dev/null | cut -d= -f2- || echo 8765)
PORT=${PORT:-8765}

pkill -f "python.*server.py" 2>/dev/null && echo "stopped server" || echo "no server running"
ps aux | grep -E "cloudflared tunnel.*localhost:$PORT|cloudflared tunnel --url http://localhost:$PORT" | grep -v grep | awk '{print $2}' | xargs -I{} kill {} 2>/dev/null && echo "stopped tunnel" || echo "no tunnel running"
