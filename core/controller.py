"""
Update controller – rate-limiting broadcast layer.

Responsibilities:
  - Maintain the set of connected WebSocket clients
  - Run a fixed-frequency loop (default 20 FPS) that reads the SharedState
    and broadcasts a JSON payload to every client
  - Silently remove clients that have disconnected
"""

import asyncio
import json
from typing import Set

from aiohttp import web

from core.state import SharedState


class UpdateController:
    """
    Throttles the telemetry broadcast to *target_fps* frames per second.

    BeamNG can send 50–200 updates/sec; browsers need at most ~30 FPS.
    This controller decouples the two rates so neither side is overloaded.
    """

    def __init__(self, shared_state: SharedState, target_fps: int = 20) -> None:
        self._state = shared_state
        self._interval = 1.0 / max(1, target_fps)
        self._clients: Set[web.WebSocketResponse] = set()
        self._running = False

    # ── Client registry ──────────────────────────────────────────────────────

    def add_client(self, ws: web.WebSocketResponse) -> None:
        """Register a new WebSocket client to receive broadcasts."""
        self._clients.add(ws)

    def remove_client(self, ws: web.WebSocketResponse) -> None:
        """Unregister a WebSocket client (called on disconnect)."""
        self._clients.discard(ws)

    # ── Broadcast loop ────────────────────────────────────────────────────────

    async def broadcast_loop(self) -> None:
        """
        Coroutine that runs indefinitely, broadcasting state at a fixed rate.

        Schedule via ``asyncio.create_task(controller.broadcast_loop())``.
        """
        self._running = True
        while self._running:
            await asyncio.sleep(self._interval)

            if not self._clients:
                continue

            state = self._state.get()
            payload = json.dumps(
                {
                    "speed": round(state.speed, 1),
                    "rpm": round(state.rpm, 0),
                    "gear": state.gear,
                    "throttle": round(state.throttle, 3),
                    "brake": round(state.brake, 3),
                    "fuel": round(state.fuel, 3),
                    "maxRpm": round(state.max_rpm, 0),
                    "airSpeed": round(state.air_speed, 1),
                    "clutch": round(state.clutch, 3),
                    "turbo": round(state.turbo, 3),
                    "engTemp": round(state.eng_temp, 1),
                    "wheelPower": round(state.wheel_power, 3),
                }
            )

            dead: Set[web.WebSocketResponse] = set()
            for ws in list(self._clients):
                try:
                    await ws.send_str(payload)
                except Exception:
                    dead.add(ws)

            self._clients -= dead

    def stop(self) -> None:
        """Signal the broadcast loop to exit on the next iteration."""
        self._running = False
