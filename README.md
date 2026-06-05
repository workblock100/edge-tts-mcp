# Edge TTS MCP

Free, high-quality neural text-to-speech as a Claude custom connector. Audio plays
**inline in the chat** through an MCP App iframe — no money, no API keys.

Uses Microsoft's neural voices via the open-source `edge-tts` library.

## What it gives you

Two tools claude.ai will see:

- **`speak(text, voice?, rate?, pitch?)`** — generates audio and renders an inline
  player widget right in the conversation. The audio autoplays (when the browser
  allows it) and the player shows the voice, the source text, and standard play
  controls.
- **`list_voices(language?)`** — lists every neural voice for a locale prefix
  (`en`, `en-GB`, `es-MX`, etc.).

Recommended voices: `en-US-AriaNeural` (default, warm female), `en-US-GuyNeural`
(male), `en-US-JennyNeural` (friendly female), `en-GB-SoniaNeural` (British female),
`en-GB-RyanNeural` (British male).

## One-time setup

```bash
cd ~/Documents/edge-tts-mcp
./bootstrap.sh   # writes .env with a fresh MCP_SECRET, installs deps
```

## Run

```bash
./start.sh   # starts uvicorn server + cloudflared tunnel, prints the connector URL
./stop.sh    # stops both
```

`start.sh` rotates the `PUBLIC_URL` in `.env` automatically. The cloudflared URL
changes every restart, so you'll need to update the connector URL in claude.ai
each time the tunnel comes back up. Logs at `/tmp/edge-tts-mcp.log` and
`/tmp/edge-tts-cf.log`.

## Add to claude.ai

1. Open <https://claude.ai/settings/connectors>.
2. Click **Add custom connector**.
3. Paste the `Claude connector URL` printed by `start.sh` (looks like
   `https://<random>.trycloudflare.com/<secret>/mcp`).
4. Authentication: **None**.
5. Save. The next time you open a chat, the `speak` and `list_voices` tools will
   be available.

## How the inline player works

Tool calls return base64-encoded MP3 in `_meta.audio_base64`. The `speak` tool
declares `_meta.ui.resourceUri = "ui://edge-tts/player.html"` — an MCP App
resource served by this server. claude.ai renders that HTML in a sandboxed iframe
inside the chat, the iframe receives the tool result via the MCP App
`postMessage` protocol, decodes the base64 to a `Blob`, sets it on an
`<audio controls>` element, and tries to autoplay.

## Troubleshooting

- **No tools showing up in Claude** — re-check the connector URL includes
  `/<MCP_SECRET>/mcp` at the end. Without the secret path you'll get a 404.
- **Tunnel URL keeps changing** — that's how Cloudflare quick tunnels work
  (free, account-less). Either accept it and re-paste the URL after each
  `start.sh` run, or set up a named tunnel via `cloudflared tunnel login`.
- **"Failed to initialize" in the player** — usually means the iframe couldn't
  load `https://esm.sh/@modelcontextprotocol/ext-apps`. Check the iframe console
  via the host's devtools.
- **Audio doesn't autoplay** — browser autoplay policy. The `<audio controls>`
  element shows a play button you can click.
