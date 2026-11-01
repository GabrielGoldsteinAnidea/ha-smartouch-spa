"""Protocol profile: every protocol fact that must come from captures.

Nothing in this file is verified yet. The defaults are deliberately EMPTY so
that the integration runs in *discovery mode* (subscribe to every notifying
characteristic and log raw traffic) until the user fills in values learned
from the app (see docs/REVERSE_ENGINEERING.md). Once values are confirmed,
they should be committed here as the defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .seven_segment import SegmentMap, SevenSegmentDecoder


class Button(StrEnum):
    """Keypad buttons the app can press.

    This is the minimal feature set (temperature, filter, light) plus jets.
    The real ACC keypad button set has not been confirmed.
    """

    TEMP_UP = "temp_up"
    TEMP_DOWN = "temp_down"
    LIGHT = "light"
    FILTER = "filter"
    JETS = "jets"


@dataclass
class ProtocolProfile:
    notify_uuid: str | None = None
    write_uuid: str | None = None
    write_with_response: bool = False
    # Button -> exact bytes the app writes for that press.
    buttons: dict[Button, bytes] = field(default_factory=dict)
    # Only frames starting with this prefix carry display data (None = all).
    display_prefix: bytes | None = None
    # Where the digit bytes sit inside a display frame.
    display_offset: int = 0
    display_length: int = 0
    # Segment bit order, bit0 upward (see SegmentMap.from_order).
    segment_order: str = "abcdefg."

    @property
    def can_read_display(self) -> bool:
        return self.notify_uuid is not None and self.display_length > 0

    def can_press(self, button: Button) -> bool:
        return self.write_uuid is not None and button in self.buttons

    def decoder(self) -> SevenSegmentDecoder:
        return SevenSegmentDecoder(SegmentMap.from_order(self.segment_order))

    def extract_display(self, frame: bytes) -> bytes | None:
        if not self.can_read_display:
            return None
        if self.display_prefix is not None and not frame.startswith(self.display_prefix):
            return None
        end = self.display_offset + self.display_length
        if len(frame) < end:
            return None
        return frame[self.display_offset : end]


def parse_hex(value: str) -> bytes:
    """Parse "AA 01 ff", "aa01ff" or "aa:01:ff" into bytes."""
    cleaned = value.replace(" ", "").replace(":", "").replace("0x", "")
    if not cleaned:
        return b""
    return bytes.fromhex(cleaned)


DEFAULT_PROFILE = ProtocolProfile()
