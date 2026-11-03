"""Interpretation of decoded display text and tracking of spa state.

The spa panel shows a single text field. Depending on context it shows the
water temperature, the set point, a clock, or a status/error code. Because
only the display is available, state must be inferred from *what* is shown
and *when*.

Display text comes from spa_core.protocol.parse_display, e.g. "102°F",
" 99°F", "38.5°C", "12:30". The app's code shows the unit glyph is the
rightmost digit and a degree dot precedes it (see docs/PROTOCOL.md).

ASSUMPTIONS (not yet verified on a real spa; see docs/PROTOCOL.md):
  * After a set point change the display shows the set point for a few
    seconds (``setpoint_window``), then returns to water temperature.
  * "h:mm" with the colon lit is the time of day, with the AM light telling
    AM from PM. The manuals say the panel shows the time of day for the first
    10 seconds of every minute once it has been set.
  * Messages such as "ECon" alternate with the temperature (ECon was seen once
    a minute), so a message counts as current for ``STATUS_WINDOW`` seconds.
"""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum

from . import status as status_mod

_TEMP_RE = re.compile(r"^\s*(\d{1,3}(?:\.\d)?)\s*°?\s*([FC])?\s*$")

_CLOCK_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*$")

# Seconds a status message stays "current" after it was last shown.
STATUS_WINDOW = 90.0

# A light that changed this many times within BLINK_WINDOW seconds is
# flashing. On the owner's spa the Filtering light flashed at about 1 Hz
# (on ~0.3 s, off ~0.7 s) with pauses of up to 7 s; the Edit light flashes
# while a menu is open.
BLINK_WINDOW = 10.0
BLINK_CHANGES = 3

# The app's spa limits are 40-104 F / 4.8-40 C (js/panel.js device_limits);
# allow a little margin so a reading slightly outside is still shown.
TEMP_RANGE_F = (32, 110)
TEMP_RANGE_C = (0, 43)


class Unit(StrEnum):
    F = "F"
    C = "C"


@dataclass(frozen=True)
class Reading:
    value: float
    unit: Unit | None  # None when the display carries no unit glyph


def parse_temperature(text: str) -> Reading | None:
    """Return the temperature if the display text is a plausible temperature."""
    match = _TEMP_RE.match(text)
    if not match:
        return None
    value = float(match.group(1))
    unit = Unit(match.group(2)) if match.group(2) else None
    if unit is Unit.C:
        lo, hi = TEMP_RANGE_C
    elif unit is Unit.F:
        lo, hi = TEMP_RANGE_F
    else:
        # Without a unit glyph, accept only values that are plausible in F.
        lo, hi = TEMP_RANGE_F
    if not lo <= value <= hi:
        return None
    return Reading(value, unit)


def parse_clock(text: str, am: bool | None) -> tuple[int, int] | None:
    """Return (hour 0-23, minute) for a time-of-day display, else None.

    ``am`` is the AM indicator light. Without it the time cannot be placed.
    """
    match = _CLOCK_RE.match(text)
    if not match or am is None:
        return None
    hour12, minute = int(match.group(1)), int(match.group(2))
    if not (1 <= hour12 <= 12 and 0 <= minute <= 59):
        return None
    hour = hour12 % 12 + (0 if am else 12)
    return hour, minute


@dataclass
class SpaState:
    display_text: str | None = None
    water_temp: Reading | None = None
    set_point: Reading | None = None
    status_text: str | None = None  # last non-temperature text (e.g. "FIL", "12:30")
    indicators: dict[str, bool] = field(default_factory=dict)
    last_frame_at: float | None = None
    last_water_temp_at: float | None = None
    last_set_point_at: float | None = None
    clock: tuple[int, int] | None = None  # (hour, minute) last shown on the panel
    clock_at: float | None = None
    # message code -> (message, monotonic time last shown)
    messages: dict[str, tuple[status_mod.Message, float]] = field(default_factory=dict)


class DisplayTracker:
    """Folds a stream of display texts into ``SpaState``."""

    def __init__(self, setpoint_window: float = 5.0, clock=time.monotonic) -> None:
        self.setpoint_window = setpoint_window
        self._clock = clock
        self._last_set_point_change: float | None = None
        self._led_changes: dict[str, deque[float]] = {}
        self.state = SpaState()

    def note_set_point_change(self) -> None:
        """Call right before sending a set point, so the next readings count as set point."""
        self._last_set_point_change = self._clock()

    def in_setpoint_window(self) -> bool:
        t = self._last_set_point_change
        return t is not None and self._clock() - t <= self.setpoint_window

    def update(self, text: str, indicators: dict[str, bool] | None = None) -> SpaState:
        now = self._clock()
        st = self.state
        st.display_text = text
        st.last_frame_at = now
        if indicators is not None:
            for name, on in indicators.items():
                if st.indicators.get(name, on) != on:
                    self._led_changes.setdefault(name, deque(maxlen=BLINK_CHANGES * 4)).append(now)
            st.indicators = dict(indicators)
        reading = parse_temperature(text)
        if reading is None:
            if text.strip():
                st.status_text = text
                clock = parse_clock(text, st.indicators.get("am"))
                if clock is not None:
                    st.clock, st.clock_at = clock, now
                message = status_mod.classify(text)
                if message is not None:
                    st.messages[message.code] = (message, now)
            # Blank text while in the window is a "flash off" of the set point.
            return st
        if self.in_setpoint_window():
            st.set_point = reading
            st.last_set_point_at = now
        else:
            st.water_temp = reading
            st.last_water_temp_at = now
        return st

    # ----------------------------------------------------------------- lights
    def led_flashing(self, name: str) -> bool:
        now = self._clock()
        changes = self._led_changes.get(name, ())
        return sum(1 for t in changes if now - t <= BLINK_WINDOW) >= BLINK_CHANGES

    def led(self, name: str) -> bool | None:
        """A light's state with flashing smoothed out: a flashing light counts as on."""
        raw = self.state.indicators.get(name)
        if raw is None:
            return None
        return True if self.led_flashing(name) else raw

    # ------------------------------------------------------------- messages
    def current_messages(self, window: float = STATUS_WINDOW) -> list[status_mod.Message]:
        """Messages shown within the last ``window`` seconds, newest first."""
        now = self._clock()
        recent = [(t, m) for m, t in self.state.messages.values() if now - t <= window]
        return [m for _, m in sorted(recent, key=lambda x: x[0], reverse=True)]

    def current_errors(self, window: float = STATUS_WINDOW) -> list[status_mod.Message]:
        return [m for m in self.current_messages(window) if m.kind is status_mod.Kind.ERROR]

    def status(self, window: float = STATUS_WINDOW) -> status_mod.Message | None:
        """The most important current message: an error, then programming, then economy."""
        current = self.current_messages(window)
        for kind in (status_mod.Kind.ERROR, status_mod.Kind.PROGRAMMING, status_mod.Kind.ECONOMY):
            for m in current:
                if m.kind is kind:
                    return m
        return None

    def estimated_clock(self) -> tuple[int, int] | None:
        """The spa's time of day now, from the last time it was shown."""
        st = self.state
        if st.clock is None or st.clock_at is None:
            return None
        minutes = st.clock[0] * 60 + st.clock[1] + int((self._clock() - st.clock_at) // 60)
        minutes %= 24 * 60
        return minutes // 60, minutes % 60
