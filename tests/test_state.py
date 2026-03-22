"""
Unit tests for the SharedState core component.
"""

from telemetry.receiver import TelemetryState
from core.state import SharedState


class TestSharedState:
    def setup_method(self):
        self.state = SharedState()

    def test_initial_state_is_telemetry_state(self):
        assert isinstance(self.state.get(), TelemetryState)

    def test_initial_speed_is_zero(self):
        assert self.state.get().speed == 0.0

    def test_initial_rpm_is_zero(self):
        assert self.state.get().rpm == 0.0

    def test_update_replaces_state(self):
        new_state = TelemetryState(speed=120.0, rpm=5000.0, gear=3)
        self.state.update(new_state)
        result = self.state.get()
        assert result.speed == 120.0
        assert result.rpm == 5000.0
        assert result.gear == 3

    def test_multiple_updates_keeps_latest(self):
        self.state.update(TelemetryState(speed=50.0))
        self.state.update(TelemetryState(speed=80.0))
        self.state.update(TelemetryState(speed=130.0))
        assert self.state.get().speed == 130.0

    def test_get_returns_same_instance_when_not_updated(self):
        s1 = self.state.get()
        s2 = self.state.get()
        assert s1 is s2
