"""Messages the spa panel shows instead of a temperature.

Codes and meanings are summarized from the ACC SmarTouch Digital manuals:
the User Manual (Rev. 05/2017, pages 5, 12-16, 25) and the Series 1000 & 2000
User & Programming Manual (pages 12-22). Whether this module's display shows
each one exactly as printed is not confirmed: only "ECon" has been seen on a
real spa so far (docs/PROTOCOL.md).

A 7-segment display cannot tell S from 5, O from 0, I from 1 or G from 6,
and shows some letters only in lower case, so codes are compared after
``normalize``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

_ALIASES = str.maketrans({"S": "5", "O": "0", "I": "1", "G": "6"})


def normalize(text: str) -> str:
    """Upper-case, drop spaces, dots, colons and degree signs, fold look-alike glyphs."""
    return re.sub(r"[\s.:°]", "", text).upper().translate(_ALIASES)


class Kind(StrEnum):
    ECONOMY = "economy"
    ERROR = "error"
    PROGRAMMING = "programming"


@dataclass(frozen=True)
class Message:
    code: str  # stable id used in Home Assistant
    kind: Kind
    description: str


# Printed code (as in the manuals) -> message.
_MESSAGES: dict[str, Message] = {
    "ECon": Message("economy", Kind.ECONOMY, "Economy mode: idle, water sampled every economy cycle"),
    "CoLd": Message("cold", Kind.ERROR, "Water below 40 F; heater status unknown, low pump runs"),
    "OH": Message("overheat", Kind.ERROR, "Water above 108 F; do not use the spa"),
    "HLoH": Message("high_limit", Kind.ERROR, "High-limit sensor tripped or disconnected; press SET once fixed"),
    "HLer": Message("high_limit", Kind.ERROR, "High-limit sensor tripped or disconnected; press SET once fixed"),
    "SEoP": Message("sensor_open", Kind.ERROR, "Temperature sensor open or disconnected; heater disabled"),
    "SESH": Message("sensor_short", Kind.ERROR, "Temperature sensor shorted; heater disabled"),
    "PSoC": Message("no_flow_circulation", Kind.ERROR, "No water pressure with the circulation pump on"),
    "PSoL": Message("no_flow_low", Kind.ERROR, "No water pressure with the low-speed jets on"),
    "PSoH": Message("no_flow_high", Kind.ERROR, "No water pressure with the high-speed jets on"),
    "toE": Message("timeout_error", Kind.ERROR, "Controller heartbeat time-out; all devices off"),
}
_BY_NORMALIZED = {normalize(k): v for k, v in _MESSAGES.items()}

# Parameter and option menu messages (SET+DOWN and UP+DOWN menus).
_PROGRAMMING_RE = re.compile(r"^(FP[1-4]D?|51LD?|CLDN|ECL|CHCL|UT0|PUF|CALB|5END|CANC|[UP][1-8][01]?|D[1-8])$")
PROGRAMMING = Message("programming", Kind.PROGRAMMING, "Panel is in a programming menu")

ERROR_CODES: tuple[str, ...] = tuple(dict.fromkeys(m.code for m in _MESSAGES.values() if m.kind is Kind.ERROR))


def classify(text: str) -> Message | None:
    """Return the message a display text shows, or None if it is not a known one."""
    norm = normalize(text)
    if not norm:
        return None
    if norm in _BY_NORMALIZED:
        return _BY_NORMALIZED[norm]
    if _PROGRAMMING_RE.match(norm):
        return PROGRAMMING
    return None
