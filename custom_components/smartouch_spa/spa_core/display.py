"""Interpretation of decoded display text and tracking of spa state.

The spa panel shows a single text field. Depending on context it shows the
water temperature, the set point, a clock, or a status/error code. Because
only the display is available, state must be inferred from *what* is shown
and *when*.

Display text comes from spa_core.protocol.parse_display, e.g. "102°F",
" 99°F", "38.5°C", "12:30". The app's code shows the unit glyph is the
rightmost digit and a degree dot precedes it (see docs/PROTOCOL.md).

ASSUMPTION (not yet verified on a real spa; see docs/PROTOCOL.md):
  * After a set point change the display shows the set point for a few
    seconds (``setpoint_window``), then returns to water temperature.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import StrEnum

_TEMP_RE = re.compile(r"^\s*(\d{1,3}(?:\.\d)?)\s*°?\s*([FC])?\s*$")

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


class DisplayTracker:
    """Folds a stream of display texts into ``SpaState``."""

    def __init__(self, setpoint_window: float = 5.0, clock=time.monotonic) -> None:
        self.setpoint_window = setpoint_window
        self._clock = clock
        self._last_set_point_change: float | None = None
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
            st.indicators = dict(indicators)
        reading = parse_temperature(text)
        if reading is None:
            if text.strip():
                st.status_text = text
            # Blank text while in the window is a "flash off" of the set point.
            return st
        if self.in_setpoint_window():
            st.set_point = reading
            st.last_set_point_at = now
        else:
            st.water_temp = reading
            st.last_water_temp_at = now
        return st
