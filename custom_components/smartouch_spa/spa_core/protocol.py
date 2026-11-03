"""SmarTouch BWF-200 BLE protocol: constants and codecs.

Every value here was read from the SmarTouch Digital app's own source
(Android package com.mltech.agi.accslv2a, version 1.1.2, a Cordova app whose
logic is JavaScript in assets/www/js/). docs/PROTOCOL.md cites the file and
line for each one and says which facts are still unconfirmed on a real spa.

This module does not depend on Home Assistant or bleak.
"""

from __future__ import annotations

import base64
import secrets
from dataclasses import dataclass, field
from enum import StrEnum

from .seven_segment import SevenSegmentDecoder

# ---------------------------------------------------------------- GATT (js/connection.js)
SERVICE_UUID = "c5a092a5-2202-4ac6-8734-2e8ff796094d"
CHAR_KEYBOARD = "12ead13c-4d06-48b7-a3f9-cdf725acdd87"
CHAR_TEMPERATURE = "0daecf8f-2352-4ae8-bdb8-4ae862f041e3"
CHAR_TIME = "8cea517c-2d76-4190-ae05-2e222a3caacb"
CHAR_DISPLAY = "30105eb3-19dc-4621-a227-a917b43162a6"
CHAR_VERSION = "207da212-c2fd-43b5-9664-ac15166364d2"
CHAR_WIFIMAC = "aefc6b90-26f1-4842-b720-3d47f4a087cf"
CHAR_MMODE = "984cdbfb-446b-43b2-a879-c857a9a0f638"
CHAR_MCODE = "6436e996-e573-4ff7-83fd-d0ea0bd09458"
CHAR_BTNAME = "f8733ee9-6e45-485a-a8a1-9e4e8bdb0536"
CHAR_WIFICREDS = "5eb76cac-ada4-43c2-9ed0-b80547542e9f"
CHAR_CRAS = "71d67ace-65d6-4d28-b08f-f54735e7d50c"

# Characteristics that change the module's configuration (master code, name,
# WiFi credentials). The raw-write service refuses them.
PROTECTED_CHARS = frozenset({CHAR_MMODE, CHAR_MCODE, CHAR_BTNAME, CHAR_WIFICREDS})

# The app uses ble.write (write with response) for every write.
WRITE_WITH_RESPONSE = True


# ---------------------------------------------------------------- buttons (js/panel.js)
class Key(StrEnum):
    """Keypad keys drawn by the app's spa layout (window.frames.spa).

    The values are the app's own names. On the spa-side panel (ACC SmarTouch
    Digital manual, KP-2000/2020 panel):

    * ``jets``   JETS key, under the Jets Lo/Hi lights
    * ``aux``    AIR key under the Air lights in the loaded ``spa`` layout,
      but under the Jets 2 lights in the unused ``spa_bluetooth`` layout
    * ``aux2``   AUX key, the other way round
    * ``light``  LITE key
    * ``system`` SET key ("done using the spa")

    docs/PROTOCOL.md has the positions. Only a press test settles aux/aux2.

    The app's buttons_codes table also has u0/d0/u1/d1 (up, down, set-temp,
    set-time), drawn only by the unused ``spa_bluetooth`` layout, so the
    shipping app never sends them. They are exposed as plain presses for the
    owner to test by hand (the panel itself limits the set point). There is no
    filter key, and there are no codes for key combinations (programming menus).
    """

    LIGHT = "light"
    JETS = "jets"
    AUX = "aux"
    AUX2 = "aux2"
    SYSTEM = "system"
    UP = "up"
    DOWN = "down"
    SET_TEMP = "set_temp"
    SET_TIME = "set_time"


KEY_CODES: dict[Key, str] = {
    Key.LIGHT: "l0",
    Key.JETS: "j0",
    Key.AUX: "a0",
    Key.AUX2: "x0",
    Key.SYSTEM: "s0",
    Key.UP: "u0",
    Key.DOWN: "d0",
    Key.SET_TEMP: "u1",
    Key.SET_TIME: "d1",
}


def encode_key(key: Key) -> bytes:
    return KEY_CODES[key].encode("ascii")


# UP and DOWN (TEMP and TIME keys). They are in the app's buttons_codes table
# and drawn by its spa_bluetooth layout, but the shipping app never loads that
# layout, so they have not been seen in use. The integration sends them only
# to step through a menu someone has already opened at the panel, checking
# the display after every press.
MENU_UP = encode_key(Key.UP)
MENU_DOWN = encode_key(Key.DOWN)


# Indicator lights that show each device key's state: (Lo light, Hi light).
# Pairing from the positions of the keys and lights in window.frames.spa.
# window.frames.spa_bluetooth swaps aux and aux2; unconfirmed until tested.
KEY_LEDS: dict[Key, tuple[str, str]] = {
    Key.JETS: ("jets_low", "jets_high"),
    Key.AUX: ("air_low", "air_high"),
    Key.AUX2: ("jets2_low", "jets2_high"),
}


# ---------------------------------------------------------------- clock (js/panel.js, js/transmitter.js)
def encode_time(hour: int, minute: int) -> bytes:
    """Encode the time of day the way the app's "Set Current Time" page does.

    The page formats the time with toLocaleString(en-US, hour12) and
    transmitter.parse_time() turns "7:45 PM" into "0745P": 12-hour clock,
    hour and minute zero-padded to 2 digits, then "A" or "P".
    """
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"invalid time {hour}:{minute}")
    hour12 = hour % 12 or 12
    return f"{hour12:02d}{minute:02d}{'A' if hour < 12 else 'P'}".encode("ascii")


# ---------------------------------------------------------------- set point (js/panel.js)
TEMP_MIN_F = 40
TEMP_MAX_F = 104


def f_to_c_app(f: int) -> float:
    """The app's own F->C conversion (panel.f2c), including its rounding."""
    tenths = (f - 1) * 11 / 2 - 166 if f % 2 else f * 11 / 2 - 172
    return round(tenths * 0.1, 1)


# The only Celsius values the app ever offers (and therefore sends).
APP_CELSIUS_VALUES: tuple[float, ...] = tuple(f_to_c_app(f) for f in range(TEMP_MIN_F, TEMP_MAX_F + 1))


def nearest_app_celsius(value: float) -> float:
    return min(APP_CELSIUS_VALUES, key=lambda c: abs(c - value))


def encode_temperature(value: float, unit: str) -> bytes:
    """Encode a set point exactly as the app does.

    F: integer, zero-padded to 3 digits, then "F" ("102F", "099F").
    C: tenths of a degree, zero-padded to 3 digits, then "C" ("385C").
    Only values the app itself offers are accepted.
    """
    if unit == "F":
        if value != int(value) or not TEMP_MIN_F <= value <= TEMP_MAX_F:
            raise ValueError(f"{value} F is outside the app's range {TEMP_MIN_F}-{TEMP_MAX_F} F")
        text = f"{int(value):03d}F"
    elif unit == "C":
        if round(value, 1) not in APP_CELSIUS_VALUES:
            raise ValueError(f"{value} C is not a value the app offers (use nearest_app_celsius)")
        text = f"{round(value * 10):03d}C"
    else:
        raise ValueError(f"unit must be 'F' or 'C', not {unit!r}")
    return text[-4:].encode("ascii")


# ---------------------------------------------------------------- auth (js/navigation.js, js/accp.js)
class MMode(StrEnum):
    """Auth state the module notifies on CHAR_MMODE."""

    FREE = "F"  # not set up yet: the app shows its setup page
    PIN_REQUIRED = "B"  # PIN needed or wrong
    MASTER = "M"
    NORMAL = "N"


def generate_mcode() -> str:
    """A 16-char base64url string from 12 random bytes, like RandomBase64url()."""
    return base64.urlsafe_b64encode(secrets.token_bytes(12)).decode("ascii")


def split_ble_string(text: str) -> list[str]:
    """Chunk a string the way the app's splitter() does.

    19 chars or fewer: one chunk, no flag. Longer: "0" + first 19, "2" + each
    middle 19, "9" + the rest.
    """
    parts = [text[i : i + 19] for i in range(0, len(text), 19)] or [""]
    if len(parts) == 1:
        return parts
    return ["0" + parts[0], *("2" + p for p in parts[1:-1]), "9" + parts[-1]]


def auth_writes(mcode: str, pin: str) -> list[bytes]:
    """The MCODE writes the app's PIN page sends: mcode + 4-digit PIN, chunked."""
    if len(pin) != 4 or not pin.isdigit():
        raise ValueError("PIN must be 4 digits")
    return [chunk.encode("ascii") for chunk in split_ble_string(mcode + pin)]


# ---------------------------------------------------------------- display (js/panel.js display())
DISPLAY_FRAME_LEN = 6

# (byte index, bit) -> indicator name, from panel.init_leds().
INDICATOR_BITS: dict[str, tuple[int, int]] = {
    "heating": (4, 0),
    "air_high": (4, 1),
    "jets_low": (4, 2),
    "jets_high": (4, 3),
    "filtering": (4, 4),
    "edit": (4, 5),
    "overheat": (4, 6),
    "am": (4, 7),
    "light": (5, 4),
    "jets2_high": (5, 5),
    "jets2_low": (5, 6),
    "air_low": (5, 7),
}

_DECODER = SevenSegmentDecoder()  # bit0=a ... bit6=g, bit7=dot (h)


@dataclass(frozen=True)
class DisplayFrame:
    text: str
    indicators: dict[str, bool] = field(default_factory=dict)
    raw: bytes = b""

    @property
    def unit(self) -> str | None:
        """'F' or 'C' when the rightmost digit is a unit letter."""
        return self.text[-1] if self.text[-1:] in ("F", "C") else None


def parse_display(data: bytes) -> DisplayFrame | None:
    """Decode a 6-byte DISPLAY notification.

    Bytes 0-3 are digits with byte 0 the RIGHTMOST. The dot bit means a
    decimal point after digits 3 and 2, the upper colon dot on digit 1, and a
    degree sign before the unit on digit 0 (from the dot positions in the
    app's SVG). Bytes 4-5 are indicator LEDs.
    """
    if len(data) != DISPLAY_FRAME_LEN:
        return None
    d3, d2, d1, d0 = (_DECODER.decode_digit(b) for b in (data[3], data[2], data[1], data[0]))
    colon = d2.dp and d1.dp
    out = [d3.char, "." if d3.dp else "", d2.char]
    if colon:
        out.append(":")
    elif d2.dp:
        out.append(".")
    out.append(d1.char)
    out.append("°" if d0.dp else "")
    out.append(d0.char)
    indicators = {name: bool(data[i] & (1 << bit)) for name, (i, bit) in INDICATOR_BITS.items()}
    return DisplayFrame(text="".join(out), indicators=indicators, raw=bytes(data))


def encode_display(text4: str, dots: tuple[bool, bool, bool, bool] = (False,) * 4, leds: bytes = b"\0\0") -> bytes:
    """Inverse of parse_display for tests and simulation.

    ``text4`` is 4 glyphs left to right; ``dots`` is the dot bit per glyph left to right.
    """
    if len(text4) != 4:
        raise ValueError("need exactly 4 glyphs")
    glyphs = bytearray(_DECODER.encode(text4))
    for i, dot in enumerate(dots):
        if dot:
            glyphs[i] |= 0x80
    return bytes(reversed(glyphs)) + leds
