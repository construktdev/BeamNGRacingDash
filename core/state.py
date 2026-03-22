"""
Shared state – single source of truth for the latest telemetry snapshot.

Because the entire application runs on one asyncio event loop, attribute
assignment is inherently atomic (no concurrent threads modify this object).
A simple wrapper is still provided so callers have a stable API to read and
write the state, and it is easy to add locking in the future if needed.
"""

from telemetry.receiver import TelemetryState


class SharedState:
    """
    Single source of truth for the current vehicle telemetry.

    Updated by the TelemetryReceiver callback; read by the UpdateController
    broadcast loop.
    """

    def __init__(self) -> None:
        self._state = TelemetryState()

    def update(self, state: TelemetryState) -> None:
        """Replace the stored state with a freshly parsed snapshot."""
        self._state = state

    def get(self) -> TelemetryState:
        """Return the most recent TelemetryState."""
        return self._state
