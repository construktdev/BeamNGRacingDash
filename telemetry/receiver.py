"""
Telemetry receiver layer.

Responsibilities:
  - Listen on a UDP port for BeamNG OutGauge packets
  - Parse raw bytes into a structured TelemetryState
  - Invoke a callback with the parsed state for every received packet
"""

import asyncio
import struct
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

# ─── OutGauge packet format (Little-endian) ──────────────────────────────────
# Based on the Live for Speed OutGauge protocol used by BeamNG.
#
# Offset  Size  Type            Field
#   0       4   unsigned int    Time        (ms)
#   4       4   char[4]         Car
#   8       2   unsigned short  Flags
#  10       1   unsigned char   Gear   (0=Rev, 1=N, 2=1st …)
#  11       1   unsigned char   SpareB
#  12       4   float           Speed       (m/s)
#  16       4   float           RPM
#  20       4   float           Turbo       (bar)
#  24       4   float           EngTemp     (°C)
#  28       4   float           Fuel        (0–1)
#  32       4   float           OilPressure (bar)
#  36       4   float           OilTemp     (°C)
#  40       4   unsigned int    DashLights
#  44       4   unsigned int    ShowLights
#  48       4   float           Throttle    (0–1)
#  52       4   float           Brake       (0–1)
#  56       4   float           Clutch      (0–1)
#  60      16   char[16]        Display1
#  76      16   char[16]        Display2
#  92       4   int             ID          (optional)

_FMT_WITHOUT_ID = "<I4sHBBfffffffIIfff16s16s"
_FMT_WITH_ID = "<I4sHBBfffffffIIfff16s16si"

_SIZE_WITHOUT_ID = struct.calcsize(_FMT_WITHOUT_ID)  # 92 bytes
_SIZE_WITH_ID = struct.calcsize(_FMT_WITH_ID)        # 96 bytes


@dataclass
class TelemetryState:
    """Structured snapshot of vehicle telemetry at a single point in time."""

    speed: float = 0.0       # km/h
    rpm: float = 0.0         # rev/min
    gear: int = 1            # 0=Reverse, 1=Neutral, 2=1st, 3=2nd …
    throttle: float = 0.0    # 0–1
    brake: float = 0.0       # 0–1
    fuel: float = 0.0        # 0–1
    timestamp: float = field(default_factory=time.time)


class OutGaugeParser:
    """Parses raw BeamNG OutGauge UDP payloads into TelemetryState objects."""

    def parse(self, data: bytes) -> Optional[TelemetryState]:
        """Return a TelemetryState parsed from *data*, or None on failure."""
        try:
            if len(data) >= _SIZE_WITH_ID:
                fields = struct.unpack_from(_FMT_WITH_ID, data)
            elif len(data) >= _SIZE_WITHOUT_ID:
                fields = struct.unpack_from(_FMT_WITHOUT_ID, data)
            else:
                return None

            # Positional unpacking matches the format order above.
            speed_ms = fields[5]
            rpm = fields[6]
            fuel = fields[9]
            throttle = fields[14]
            brake = fields[15]
            gear = int(fields[3])

            return TelemetryState(
                speed=speed_ms * 3.6,  # m/s → km/h
                rpm=max(0.0, rpm),
                gear=gear,
                throttle=max(0.0, min(1.0, throttle)),
                brake=max(0.0, min(1.0, brake)),
                fuel=max(0.0, min(1.0, fuel)),
                timestamp=time.time(),
            )
        except struct.error:
            return None


class _UDPProtocol(asyncio.DatagramProtocol):
    """asyncio DatagramProtocol that feeds packets to the OutGaugeParser."""

    def __init__(
        self,
        parser: OutGaugeParser,
        callback: Callable[[TelemetryState], None],
    ) -> None:
        self._parser = parser
        self._callback = callback

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        state = self._parser.parse(data)
        if state is not None:
            self._callback(state)

    def error_received(self, exc: Exception) -> None:
        pass

    def connection_lost(self, exc: Optional[Exception]) -> None:
        pass


class TelemetryReceiver:
    """
    High-level UDP receiver for BeamNG OutGauge telemetry.

    Usage::

        receiver = TelemetryReceiver(port=4444)
        receiver.set_update_callback(lambda state: ...)
        await receiver.start()
        # … application runs …
        receiver.stop()
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 4444) -> None:
        self._host = host
        self._port = port
        self._parser = OutGaugeParser()
        self._callback: Callable[[TelemetryState], None] = lambda _: None
        self._transport: Optional[asyncio.BaseTransport] = None

    def set_update_callback(
        self, callback: Callable[[TelemetryState], None]
    ) -> None:
        """Register a callback that is invoked with each parsed TelemetryState."""
        self._callback = callback

    async def start(self) -> None:
        """Bind the UDP socket and start receiving packets."""
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: _UDPProtocol(self._parser, self._callback),
            local_addr=(self._host, self._port),
        )

    def stop(self) -> None:
        """Close the UDP socket."""
        if self._transport is not None:
            self._transport.close()
            self._transport = None
