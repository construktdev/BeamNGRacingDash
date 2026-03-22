"""
Web server layer – HTTP static files + WebSocket endpoint.

HTTP  → serves the dashboard SPA (index.html, style.css, app.js)
WS    → /ws  pushes live telemetry JSON to every connected browser
"""

from pathlib import Path

from aiohttp import web

from core.controller import UpdateController
from core.state import SharedState

_STATIC_DIR = Path(__file__).parent.parent / "static"


def create_app(shared_state: SharedState, controller: UpdateController) -> web.Application:
    """
    Build and return the aiohttp Application.

    :param shared_state: The central telemetry store (passed for potential
                         future HTTP endpoints that expose a snapshot).
    :param controller:   The UpdateController that manages WebSocket clients.
    """
    app = web.Application()

    # ── WebSocket handler ─────────────────────────────────────────────────────

    async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        controller.add_client(ws)
        try:
            async for _msg in ws:
                # Client messages are ignored; the protocol is server-push only.
                pass
        finally:
            controller.remove_client(ws)
        return ws

    # ── Routes ────────────────────────────────────────────────────────────────

    async def index_handler(request: web.Request) -> web.FileResponse:
        return web.FileResponse(_STATIC_DIR / "index.html")

    app.router.add_get("/", index_handler)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_static("/static", _STATIC_DIR, name="static")

    return app
