"""
Unit tests for the telemetry receiver layer.

Covers:
  - OutGaugeParser with full (96-byte) and minimal (92-byte) packets
  - OutGaugeParser rejects packets that are too short
  - TelemetryState field values and unit conversions
  - Dynamic max RPM tracking
  - Additional telemetry fields (clutch, turbo, eng_temp, wheel_power, air_speed)
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
    turbo: float = 0.0,
    eng_temp: float = 90.0,
    clutch: float = 0.0,
    show_lights: int = 0,
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
        turbo,         # turbo
        eng_temp,      # eng_temp
        fuel,          # fuel
        3.0,           # oil_pressure
        100.0,         # oil_temp
        0,             # dash_lights
        show_lights,   # show_lights
        throttle,      # throttle
        brake,         # brake
        clutch,        # clutch
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

    # ── Additional telemetry fields ──────────────────────────────────────────

    def test_clutch_parsed(self):
        data = _make_packet(clutch=0.6)
        state = self.parser.parse(data)
        assert abs(state.clutch - 0.6) < 1e-5

    def test_clutch_clamped(self):
        data = _make_packet(clutch=-0.1)
        state = self.parser.parse(data)
        assert state.clutch >= 0.0

    def test_turbo_parsed(self):
        data = _make_packet(turbo=1.2)
        state = self.parser.parse(data)
        assert abs(state.turbo - 1.2) < 1e-4

    def test_eng_temp_parsed(self):
        data = _make_packet(eng_temp=95.5)
        state = self.parser.parse(data)
        assert abs(state.eng_temp - 95.5) < 0.1

    def test_air_speed_equals_speed(self):
        """air_speed is derived from the same source as speed."""
        data = _make_packet(speed_ms=20.0)
        state = self.parser.parse(data)
        assert abs(state.air_speed - state.speed) < 1e-4

    # ── Dynamic max RPM ───────────────────────────────────────────────────────

    def test_max_rpm_grows_with_observed_rpm(self):
        """max_rpm should increase when higher RPM is seen."""
        self.parser.parse(_make_packet(rpm=5000.0))
        state = self.parser.parse(_make_packet(rpm=7500.0))
        assert state.max_rpm >= 7500.0

    def test_max_rpm_does_not_shrink(self):
        """max_rpm must not fall when RPM drops."""
        self.parser.parse(_make_packet(rpm=9000.0))
        state = self.parser.parse(_make_packet(rpm=1000.0))
        assert state.max_rpm >= 9000.0

    def test_max_rpm_minimum_default(self):
        """max_rpm has a sensible minimum even at very low RPM."""
        state = self.parser.parse(_make_packet(rpm=100.0))
        assert state.max_rpm >= OutGaugeParser._MIN_MAX_RPM

    def test_max_rpm_is_independent_per_parser_instance(self):
        """Each parser instance maintains its own max RPM."""
        parser2 = OutGaugeParser()
        self.parser.parse(_make_packet(rpm=9000.0))
        state2 = parser2.parse(_make_packet(rpm=3000.0))
        assert state2.max_rpm < 9000.0

    # ── Wheel power ───────────────────────────────────────────────────────────

    def test_wheel_power_between_zero_and_one(self):
        data = _make_packet(throttle=0.8, rpm=5000.0)
        state = self.parser.parse(data)
        assert 0.0 <= state.wheel_power <= 1.0

    def test_wheel_power_zero_at_zero_throttle(self):
        data = _make_packet(throttle=0.0, rpm=5000.0)
        state = self.parser.parse(data)
        assert state.wheel_power == 0.0

    # ── Indicator / warning lights ────────────────────────────────────────────

    def test_indicators_off_by_default(self):
        """All indicators default to False when show_lights is 0."""
        state = self.parser.parse(_make_packet(show_lights=0))
        assert state.handbrake is False
        assert state.abs_active is False
        assert state.tc_active is False
        assert state.signal_left is False
        assert state.signal_right is False

    def test_handbrake_bit(self):
        """DL_HANDBRAKE = 0x04 sets handbrake=True."""
        state = self.parser.parse(_make_packet(show_lights=0x04))
        assert state.handbrake is True
        assert state.abs_active is False

    def test_abs_bit(self):
        """DL_ABS = 0x400 sets abs_active=True."""
        state = self.parser.parse(_make_packet(show_lights=0x400))
        assert state.abs_active is True
        assert state.handbrake is False

    def test_tc_bit(self):
        """DL_TC = 0x10 sets tc_active=True."""
        state = self.parser.parse(_make_packet(show_lights=0x10))
        assert state.tc_active is True

    def test_signal_left_bit(self):
        """DL_SIGNAL_L = 0x20 sets signal_left=True."""
        state = self.parser.parse(_make_packet(show_lights=0x20))
        assert state.signal_left is True
        assert state.signal_right is False

    def test_signal_right_bit(self):
        """DL_SIGNAL_R = 0x40 sets signal_right=True."""
        state = self.parser.parse(_make_packet(show_lights=0x40))
        assert state.signal_right is True
        assert state.signal_left is False

    def test_multiple_indicators_simultaneously(self):
        """Handbrake + ABS can both be active at the same time."""
        state = self.parser.parse(_make_packet(show_lights=0x04 | 0x400))
        assert state.handbrake is True
        assert state.abs_active is True

    def test_both_turn_signals(self):
        """Left and right signals can both be active (hazard lights)."""
        state = self.parser.parse(_make_packet(show_lights=0x20 | 0x40))
        assert state.signal_left is True
        assert state.signal_right is True
