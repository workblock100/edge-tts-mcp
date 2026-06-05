"""Edge TTS MCP server — Streamable HTTP transport for use as a Claude custom connector.

Speaks text using Microsoft's neural voices (via the free edge-tts library) and
returns audio that plays inline in the chat through an MCP App iframe.

Auth model (single-user deployment):
- The MCP endpoint is mounted under a secret URL path (MCP_SECRET) so only the
  user with the URL can call tools. No bearer token negotiation needed.
"""
from __future__ import annotations

import base64
import contextlib
import os
from pathlib import Path
from typing import Annotated

import edge_tts
import uvicorn
from dotenv import load_dotenv
from mcp import types
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route

load_dotenv()

PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")
MCP_SECRET = os.environ.get("MCP_SECRET", "")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8765"))

if not MCP_SECRET or len(MCP_SECRET) < 24:
    raise SystemExit(
        "MCP_SECRET must be set to a long random string (>=24 chars). "
        'Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
    )

VIEW_URI = "ui://edge-tts/player.v3.html"
VIEW_HTML_PATH = Path(__file__).parent / "view.html"

DEFAULT_VOICE = "en-US-AriaNeural"

mcp = FastMCP(
    "edge-tts",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
    stateless_http=True,
)


@mcp.tool(
    meta={
        "ui": {"resourceUri": VIEW_URI},
        "ui/resourceUri": VIEW_URI,  # legacy support
    }
)
async def speak(
    text: Annotated[
        str,
        Field(description="Text to read aloud. Supports SSML if it begins with <speak>."),
    ],
    voice: Annotated[
        str,
        Field(
            description=(
                "Microsoft neural voice short name. Defaults to en-US-AriaNeural. "
                "Other good picks: en-US-GuyNeural (male), en-US-JennyNeural (friendly female), "
                "en-US-EmmaNeural (warm female), en-GB-SoniaNeural (British female), "
                "en-GB-RyanNeural (British male), en-AU-NatashaNeural (Australian female). "
                "Call list_voices for the full set."
            )
        ),
    ] = DEFAULT_VOICE,
    rate: Annotated[
        str,
        Field(description='Speed adjustment, e.g. "+0%", "-20%", "+15%".'),
    ] = "+0%",
    pitch: Annotated[
        str,
        Field(description='Pitch adjustment, e.g. "+0Hz", "-10Hz", "+5Hz".'),
    ] = "+0Hz",
) -> list[types.TextContent]:
    """Speak text aloud using a high-quality neural voice. The audio plays
    inline in the chat via an embedded audio player."""
    text = text.strip()
    if not text:
        raise ValueError("text is required")

    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    audio_chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])

    if not audio_chunks:
        raise RuntimeError("Edge TTS returned no audio. Check the voice name.")

    audio_bytes = b"".join(audio_chunks)
    audio_b64 = base64.b64encode(audio_bytes).decode()

    preview = text if len(text) <= 80 else text[:77] + "..."
    return [
        types.TextContent(
            type="text",
            text=f'Speaking with {voice}: "{preview}"',
            _meta={
                "audio_base64": audio_b64,
                "mime_type": "audio/mpeg",
                "voice": voice,
                "rate": rate,
                "pitch": pitch,
                "text": text,
                "size_bytes": len(audio_bytes),
            },
        ),
    ]


@mcp.tool()
async def list_voices(
    language: Annotated[
        str,
        Field(description='Language/locale prefix to filter, e.g. "en", "en-GB", "es", "fr".'),
    ] = "en",
) -> list[types.TextContent]:
    """List available neural voices, optionally filtered by language code."""
    voices = await edge_tts.list_voices()
    if language:
        prefix = language.lower()
        voices = [v for v in voices if v["Locale"].lower().startswith(prefix)]
    voices.sort(key=lambda v: (v["Locale"], v["ShortName"]))
    lines = [f'- {v["ShortName"]}  ({v["Gender"]}, {v["Locale"]})' for v in voices]
    body = "\n".join(lines) if lines else f"No voices match prefix {language!r}."
    return [
        types.TextContent(
            type="text",
            text=f"{len(lines)} voices for {language!r}:\n{body}",
        )
    ]


@mcp.resource(
    VIEW_URI,
    mime_type="text/html;profile=mcp-app",
    meta={
        "ui": {
            "csp": {
                "resourceDomains": ["https://esm.sh", "https://unpkg.com"],
            }
        }
    },
)
def view() -> str:
    """The MCP App view: an inline audio player that consumes the tool result."""
    return VIEW_HTML_PATH.read_text()


# --- HTTP routes ------------------------------------------------------------


LANDING_HTML = """<!doctype html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Edge TTS MCP</title>
<style>
body{{font:16px/1.5 -apple-system,system-ui,sans-serif;max-width:560px;margin:40px auto;padding:0 16px;color:#111}}
code{{background:#f4f4f4;padding:2px 6px;border-radius:4px;font-size:13px;word-break:break-all}}
</style></head><body>
<h1>Edge TTS MCP</h1>
<p>Free, high-quality neural TTS for Claude — plays inline.</p>
<hr>
<p><strong>Custom connector URL:</strong></p>
<p><code>{mcp_url}</code></p>
<p style="color:#666;font-size:13px">Paste into Claude → Settings → Connectors → Add custom connector.</p>
</body></html>
"""


async def landing(_request: Request) -> HTMLResponse:
    base = PUBLIC_URL or f"http://localhost:{PORT}"
    return HTMLResponse(LANDING_HTML.format(mcp_url=f"{base}/{MCP_SECRET}/mcp"))


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


# --- App assembly -----------------------------------------------------------

mcp_app = mcp.streamable_http_app()


@contextlib.asynccontextmanager
async def lifespan(app):
    async with mcp_app.router.lifespan_context(app):
        yield


app = Starlette(
    debug=False,
    routes=[
        Route("/", landing),
        Route("/health", health),
        Mount(f"/{MCP_SECRET}", app=mcp_app),
    ],
    lifespan=lifespan,
)


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
