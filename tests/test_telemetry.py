"""
Unit tests for the telemetry receiver layer.

Covers:
  - OutGaugeParser with full (96-byte) and minimal (92-byte) packets
  - OutGaugeParser rejects packets that are too short
  - TelemetryState field values and unit conversions
"""

import struct
import time

import pytest

from telemetry.receiver import (
    OutGaugeParser,
    TelemetryState,
    _FMT_WITHOUT_ID,
    _FMT_WITH_ID,
    _SIZE_WITHOUT_ID,
    _SIZE_WITH_ID,
)


def _make_packet(
    speed_ms: float = 50.0,
    rpm: float = 3000.0,
    gear: int = 3,
    throttle: float = 0.5,
    brake: float = 0.0,
    fuel: float = 0.8,
    include_id: bool = True,
) -> bytes:
    """Build a syntactically valid OutGauge packet."""
    fmt = _FMT_WITH_ID if include_id else _FMT_WITHOUT_ID
    args = (
        1000,          # time_ms
        b"BM  ",       # car[4]
        0,             # flags
        gear,          # gear
        0,             # spare_b
        speed_ms,      # speed  (m/s)
        rpm,           # rpm
        0.0,           # turbo
        90.0,          # eng_temp
        fuel,          # fuel
        3.0,           # oil_pressure
        100.0,         # oil_temp
        0,             # dash_lights
        0,             # show_lights
        throttle,      # throttle
        brake,         # brake
        0.0,           # clutch
        b" " * 16,     # display1
        b" " * 16,     # display2
    )
    if include_id:
        args = args + (42,)  # id
    return struct.pack(fmt, *args)


class TestOutGaugeSizes:
    def test_size_without_id(self):
        assert _SIZE_WITHOUT_ID == 92

    def test_size_with_id(self):
        assert _SIZE_WITH_ID == 96


class TestOutGaugeParser:
    def setup_method(self):
        self.parser = OutGaugeParser()

    def test_parse_with_id(self):
        data = _make_packet(speed_ms=27.78, rpm=4500.0, gear=4, include_id=True)
        state = self.parser.parse(data)
        assert state is not None
        assert abs(state.speed - 27.78 * 3.6) < 0.01
        assert state.rpm == 4500.0
        assert state.gear == 4

    def test_parse_without_id(self):
        data = _make_packet(speed_ms=10.0, rpm=2000.0, gear=2, include_id=False)
        state = self.parser.parse(data)
        assert state is not None
        assert abs(state.speed - 10.0 * 3.6) < 0.01
        assert state.rpm == 2000.0

    def test_speed_conversion_ms_to_kmh(self):
        data = _make_packet(speed_ms=100.0 / 3.6)  # 100 km/h in m/s
        state = self.parser.parse(data)
        assert abs(state.speed - 100.0) < 0.01

    def test_throttle_and_brake(self):
        data = _make_packet(throttle=0.75, brake=0.3)
        state = self.parser.parse(data)
        assert abs(state.throttle - 0.75) < 1e-5
        assert abs(state.brake - 0.3) < 1e-5

    def test_fuel(self):
        data = _make_packet(fuel=0.42)
        state = self.parser.parse(data)
        assert abs(state.fuel - 0.42) < 1e-5

    def test_too_short_returns_none(self):
        assert self.parser.parse(b"\x00" * 10) is None
        assert self.parser.parse(b"") is None

    def test_exactly_92_bytes_parsed(self):
        data = _make_packet(include_id=False)
        assert len(data) == 92
        state = self.parser.parse(data)
        assert state is not None

    def test_returns_telemetry_state(self):
        state = self.parser.parse(_make_packet())
        assert isinstance(state, TelemetryState)

    def test_timestamp_is_recent(self):
        before = time.time()
        state = self.parser.parse(_make_packet())
        after = time.time()
        assert state is not None
        assert before <= state.timestamp <= after

    def test_gear_neutral(self):
        data = _make_packet(gear=1)
        state = self.parser.parse(data)
        assert state.gear == 1  # Neutral

    def test_gear_reverse(self):
        data = _make_packet(gear=0)
        state = self.parser.parse(data)
        assert state.gear == 0  # Reverse

    def test_throttle_clamped_above_one(self):
        data = _make_packet(throttle=1.5)
        state = self.parser.parse(data)
        assert state.throttle <= 1.0

    def test_brake_clamped_below_zero(self):
        data = _make_packet(brake=-0.5)
        state = self.parser.parse(data)
        assert state.brake >= 0.0
