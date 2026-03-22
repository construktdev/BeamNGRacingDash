"""
Unit tests for the UpdateController.

The controller's broadcast_loop is async, so we test it with pytest-asyncio.
WebSocket client interactions are replaced with simple async-compatible stubs.
"""

import asyncio
import json

import pytest
import pytest_asyncio

from telemetry.receiver import TelemetryState
from core.state import SharedState
from core.controller import UpdateController


class _FakeWebSocket:
    """Minimal WebSocket stub that records sent messages."""

    def __init__(self):
        self.sent: list[str] = []
        self.closed = False

    async def send_str(self, data: str) -> None:
        if self.closed:
            raise ConnectionResetError("WebSocket closed")
        self.sent.append(data)


class TestUpdateController:
    def setup_method(self):
        self.shared_state = SharedState()
        self.controller = UpdateController(self.shared_state, target_fps=100)

    def test_add_and_remove_client(self):
        ws = _FakeWebSocket()
        self.controller.add_client(ws)
        assert ws in self.controller._clients
        self.controller.remove_client(ws)
        assert ws not in self.controller._clients

    def test_remove_unknown_client_is_safe(self):
        ws = _FakeWebSocket()
        self.controller.remove_client(ws)  # should not raise

    @pytest.mark.asyncio
    async def test_broadcast_sends_json_to_client(self):
        ws = _FakeWebSocket()
        self.controller.add_client(ws)
        self.shared_state.update(TelemetryState(speed=99.9, rpm=6000.0, gear=4))

        self.controller._running = True
        # Run one iteration of the loop body manually
        await asyncio.sleep(self.controller._interval)
        state = self.shared_state.get()
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
        await ws.send_str(payload)

        assert len(ws.sent) == 1
        data = json.loads(ws.sent[0])
        assert data["speed"] == round(99.9, 1)
        assert data["rpm"] == 6000.0
        assert data["gear"] == 4
        assert "maxRpm" in data
        assert "airSpeed" in data
        assert "clutch" in data
        assert "turbo" in data
        assert "engTemp" in data
        assert "wheelPower" in data

    @pytest.mark.asyncio
    async def test_broadcast_loop_removes_dead_clients(self):
        ws = _FakeWebSocket()
        ws.closed = True  # Sending to this WS will raise
        self.controller.add_client(ws)
        self.shared_state.update(TelemetryState(speed=10.0))

        # Run loop for slightly more than one interval
        task = asyncio.create_task(self.controller.broadcast_loop())
        await asyncio.sleep(self.controller._interval * 2.5)
        self.controller.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Dead client must have been pruned
        assert ws not in self.controller._clients

    @pytest.mark.asyncio
    async def test_stop_exits_loop(self):
        task = asyncio.create_task(self.controller.broadcast_loop())
        await asyncio.sleep(self.controller._interval * 1.5)
        self.controller.stop()
        # Give the loop one more sleep to notice the stop flag
        await asyncio.sleep(self.controller._interval * 1.5)
        # The loop should have noticed the stop flag and exited
        assert task.done()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
