"""Interpretation of decoded display text and tracking of spa state.

The spa panel shows a single text field. Depending on context it shows the
water temperature, the set point (typically right after a temp button press),
or a status/error code. Because only the display is available, state must be
inferred from *what* is shown and *when*.

ASSUMPTIONS (not yet verified against captures; see docs/PROTOCOL.md):
  * After a Temp Up/Down press the display shows the set point for a few
    seconds (``setpoint_window``), then returns to water temperature. This is
    how most button-driven spa panels behave.
  * Temperatures are shown as 2-3 digits, optionally followed by "F" or "C".
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import StrEnum

_TEMP_RE = re.compile(r"^\s*(\d{2,3})(?:\.)?\s*([FC])?\s*$")

# Plausible spa ranges. Most spa controllers cap at 104F / 40C.
TEMP_RANGE_F = (40, 110)
TEMP_RANGE_C = (5, 43)


class Unit(StrEnum):
    F = "F"
    C = "C"


@dataclass(frozen=True)
class Reading:
    value: int
    unit: Unit | None  # None when the display carries no unit glyph


def parse_temperature(text: str) -> Reading | None:
    """Return the temperature if the display text is a plausible temperature."""
    match = _TEMP_RE.match(text)
    if not match:
        return None
    value = int(match.group(1))
    unit = Unit(match.group(2)) if match.group(2) else None
    if unit is Unit.C:
        lo, hi = TEMP_RANGE_C
    elif unit is Unit.F:
        lo, hi = TEMP_RANGE_F
    else:
        lo, hi = TEMP_RANGE_C[0], TEMP_RANGE_F[1]
    if not lo <= value <= hi:
        return None
    return Reading(value, unit)


@dataclass
class SpaState:
    display_text: str | None = None
    water_temp: Reading | None = None
    set_point: Reading | None = None
    status_text: str | None = None  # last non-temperature text (e.g. "FIL")
    indicators: dict[str, bool] = field(default_factory=dict)
    last_frame_at: float | None = None
    last_water_temp_at: float | None = None
    last_set_point_at: float | None = None


class DisplayTracker:
    """Folds a stream of display texts into ``SpaState``."""

    def __init__(self, setpoint_window: float = 5.0, clock=time.monotonic) -> None:
        self.setpoint_window = setpoint_window
        self._clock = clock
        self._last_temp_press: float | None = None
        self.state = SpaState()

    def note_temp_button_press(self) -> None:
        self._last_temp_press = self._clock()

    def in_setpoint_window(self) -> bool:
        return self._last_temp_press is not None and self._clock() - self._last_temp_press <= self.setpoint_window

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
