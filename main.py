"""
BeamNG Racing Dashboard – entry point.

Starts three concurrent asyncio tasks:
  1. TelemetryReceiver  – UDP socket, receives BeamNG OutGauge packets
  2. UpdateController   – rate-limited broadcast loop (20 FPS)
  3. aiohttp Web Server – HTTP (static dashboard) + WebSocket (/ws)

Environment / configuration
----------------------------
All settings use sensible defaults; override via the constants below or via
environment variables in a later iteration.

Network layout
--------------
::

    PC (this process)
      ├─ UDP  0.0.0.0:4444  ← BeamNG pushes OutGauge packets here
      └─ TCP  0.0.0.0:8080  → browser connects, opens /ws for live data
"""

import asyncio
import logging

from aiohttp import web

from core.controller import UpdateController
from core.state import SharedState
from server.app import create_app
from telemetry.receiver import TelemetryReceiver

# ── Configuration ─────────────────────────────────────────────────────────────

UDP_HOST = "0.0.0.0"
UDP_PORT = 4444

WEB_HOST = "0.0.0.0"
WEB_PORT = 8080

TARGET_FPS = 20   # broadcast rate to browsers

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
)
logger = logging.getLogger(__name__)


# ── Main coroutine ────────────────────────────────────────────────────────────

async def main() -> None:
    # 1. Shared State – single source of truth
    shared_state = SharedState()

    # 2. Update Controller – rate-limited broadcaster
    controller = UpdateController(shared_state, target_fps=TARGET_FPS)

    # 3. Telemetry Receiver – UDP input layer
    receiver = TelemetryReceiver(host=UDP_HOST, port=UDP_PORT)
    receiver.set_update_callback(shared_state.update)
    await receiver.start()
    logger.info("Telemetry receiver listening on UDP %s:%d", UDP_HOST, UDP_PORT)

    # 4. Start broadcast loop as a background task
    broadcast_task = asyncio.create_task(controller.broadcast_loop())

    # 5. Web Server – HTTP + WebSocket
    app = create_app(shared_state, controller)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_HOST, WEB_PORT)
    await site.start()
    logger.info("Dashboard available at http://%s:%d", WEB_HOST, WEB_PORT)
    logger.info("WebSocket endpoint: ws://%s:%d/ws", WEB_HOST, WEB_PORT)

    # Run until interrupted
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        controller.stop()
        broadcast_task.cancel()
        receiver.stop()
        await runner.cleanup()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
