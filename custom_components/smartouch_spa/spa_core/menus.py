"""The panel's two programming menus: layout, settings, and passive capture.

Menu order and labels were read off the owner's spa on 2026-11-02 while the
owner scrolled both menus at the panel (integration diagnostics):

* Parameter menu (opened with SET+DOWN on the panel): FP1 FP2 FP3 FP4 FP1d
  FP2d FP3d FP4d CLdn ECL CHCL Uto PUF SEnd CAnC, circular. This firmware
  has no SIL, SILd or CALb, which the manuals list.
* Options menu (UP+DOWN): U1-U8, P1-P8, d1-d8, CAnC, SEnd, circular. Each
  U/P label carries its value ("P8 1").

The Edit light blinks while either menu is open. Meanings, ranges and units
are from the SmarTouch Digital manuals (Programming Manual pages 13-20).

Capture is passive: whatever the panel shows while someone uses a menu is
recorded. The first value seen for an item in a session is what was stored
before any edit; the last value is what was saved if the session ended on
SEnd. Ending on CAnC or by time-out keeps the first values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from .status import normalize


class Menu(StrEnum):
    PARAMETERS = "parameters"
    OPTIONS = "options"


class Kind(StrEnum):
    TIME = "time"  # h:mm with the AM light
    NUMBER = "number"
    FLAG = "flag"  # U/P options, 0 or 1
    READING = "reading"  # D values, read-only


@dataclass(frozen=True)
class Setting:
    code: str  # as printed on the panel, e.g. "FP1d"
    menu: Menu
    kind: Kind
    name: str
    min: int | None = None
    max: int | None = None
    unit: str | None = None
    writable: bool = True


def _param(code, kind, name, lo=None, hi=None, unit=None):
    return Setting(code, Menu.PARAMETERS, kind, name, lo, hi, unit)


PARAMETERS: tuple[Setting, ...] = (
    _param("FP1", Kind.TIME, "Filtration 1 start"),
    _param("FP2", Kind.TIME, "Filtration 2 start"),
    _param("FP3", Kind.TIME, "Filtration 3 start"),
    _param("FP4", Kind.TIME, "Filtration 4 start"),
    _param("FP1d", Kind.NUMBER, "Filtration 1 duration", 0, 240, "min"),
    _param("FP2d", Kind.NUMBER, "Filtration 2 duration", 0, 240, "min"),
    _param("FP3d", Kind.NUMBER, "Filtration 3 duration", 0, 240, "min"),
    _param("FP4d", Kind.NUMBER, "Filtration 4 duration", 0, 240, "min"),
    _param("CLdn", Kind.NUMBER, "Cool-down", 30, 180, "s"),
    _param("ECL", Kind.NUMBER, "Economy cycle", 60, 240, "min"),
    _param("CHCL", Kind.NUMBER, "Channel clear", 0, 180, "s"),
    _param("Uto", Kind.NUMBER, "User time-out", 10, 60, "min"),
    _param("PUF", Kind.NUMBER, "Post-use filtration", 30, 180, "min"),
)

_U_NAMES = {
    1: "Auto maintenance instead of economy",
    2: "Low pump always on",
    3: "Two auto-filtration periods",
    4: "User timer restarts on every key",
    5: "Hide time of day",
    6: "Unit opposite to line frequency",
    7: "Reserved U7",
    8: "Reserved U8",
}
_P_NAMES = {
    1: "Circulation pump fitted",
    2: "Primary pump single speed",
    3: "Low power mode",
    4: "Light key 3-function",
    5: "Reserved P5",
    6: "Air blower disabled",
    7: "Secondary pump dual speed",
    8: "Two secondary pumps",
}
_D_NAMES = {
    1: "Relative temperature reading",
    2: "Key reading",
    3: "Relay output",
    4: "Temperature error count",
    5: "High-limit error count",
    6: "Heartbeat error count",
    7: "Firmware revision",
    8: "Manufacture date (yyww)",
}

OPTIONS: tuple[Setting, ...] = (
    # U7/U8 are reserved ("do not change"); P options are protected: a wrong
    # P7/P8 can destroy pump motors (manual page 20). Neither is ever written.
    *(Setting(f"U{i}", Menu.OPTIONS, Kind.FLAG, _U_NAMES[i], 0, 1, writable=i <= 6) for i in range(1, 9)),
    *(Setting(f"P{i}", Menu.OPTIONS, Kind.FLAG, _P_NAMES[i], 0, 1, writable=False) for i in range(1, 9)),
    *(Setting(f"d{i}", Menu.OPTIONS, Kind.READING, _D_NAMES[i], writable=False) for i in range(1, 9)),
)

SETTINGS: dict[str, Setting] = {s.code: s for s in (*PARAMETERS, *OPTIONS)}

PARAMETER_ORDER: tuple[str, ...] = (*(s.code for s in PARAMETERS), "SEnd", "CAnC")
OPTION_ORDER: tuple[str, ...] = (*(s.code for s in OPTIONS), "CAnC", "SEnd")
ORDER = {Menu.PARAMETERS: PARAMETER_ORDER, Menu.OPTIONS: OPTION_ORDER}

_NORM_TO_CODE = {normalize(c): c for c in (*PARAMETER_ORDER, *OPTION_ORDER)}
_FLAG_RE = re.compile(r"^([UP][1-8])([01])$")
_NUMBER_RE = re.compile(r"^\s*(\d{1,4})\s*$")
_TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*$")


@dataclass(frozen=True)
class Label:
    code: str
    menu: Menu | None  # None for SEnd/CAnC, which both menus have
    value: int | None = None  # U/P labels carry their value


def parse_label(text: str) -> Label | None:
    """Return the menu item a display text names, or None for a value screen."""
    norm = normalize(text)
    m = _FLAG_RE.match(norm)
    if m:
        return Label(m.group(1), Menu.OPTIONS, int(m.group(2)))
    code = _NORM_TO_CODE.get(norm)
    if code is None:
        return None
    if code in ("SEnd", "CAnC"):
        return Label(code, None)
    return Label(code, SETTINGS[code].menu)


def parse_value(setting: Setting, text: str, am: bool | None) -> int | str | None:
    """Parse a value screen for ``setting``. Times come back as "HH:MM" (24 h)."""
    if setting.kind is Kind.TIME:
        m = _TIME_RE.match(text)
        if not m or am is None:
            return None
        hour12, minute = int(m.group(1)), int(m.group(2))
        if not (1 <= hour12 <= 12 and minute <= 59):
            return None
        return f"{hour12 % 12 + (0 if am else 12):02d}:{minute:02d}"
    m = _NUMBER_RE.match(text)
    return int(m.group(1)) if m else None


def neighbours(menu: Menu, code: str) -> tuple[str, str]:
    """(next, previous) item in the circular menu."""
    order = ORDER[menu]
    i = order.index(code)
    return order[(i + 1) % len(order)], order[(i - 1) % len(order)]


@dataclass
class _Session:
    menu: Menu | None = None
    first: dict[str, int | str] = field(default_factory=dict)
    last: dict[str, int | str] = field(default_factory=dict)
    last_label: str | None = None
    last_label_at: float = 0.0


class MenuTracker:
    """Follows the display through a menu session and records what it shows.

    ``on_commit(values)`` is called when a session ends, with the values that
    are now stored in the controller (see module docstring).
    """

    # A menu counts as open while the Edit light was lit this recently.
    EDIT_HOLD = 2.0
    # SET on SEnd closes the menu at once; the 60 s time-out closes it later.
    SAVE_WINDOW = 8.0

    def __init__(self, on_commit=None) -> None:
        self.on_commit = on_commit
        self.session: _Session | None = None
        self.label: Label | None = None  # current menu item while open
        self.value: int | str | None = None  # value on the current value screen
        self._edit_at: float | None = None

    @property
    def open(self) -> bool:
        return self.session is not None

    @property
    def menu(self) -> Menu | None:
        return None if self.session is None else self.session.menu

    @property
    def on_value_screen(self) -> bool:
        return self.open and self.value is not None

    def update(self, text: str, indicators: dict[str, bool], now: float) -> None:
        if indicators.get("edit"):
            self._edit_at = now
        label = parse_label(text)
        edit_recent = self._edit_at is not None and now - self._edit_at <= self.EDIT_HOLD
        if label is not None and (edit_recent or self.session is not None):
            self._on_label(label, now)
            return
        if self.session is None:
            return
        if not edit_recent:
            self.end(now)
            return
        # A value screen for the current item (blank frames are flashing).
        if text.strip() and self.label is not None and self.label.code in SETTINGS:
            setting = SETTINGS[self.label.code]
            value = parse_value(setting, text, indicators.get("am"))
            if value is not None:
                self.value = value
                self._record(setting.code, value)

    def check_timeout(self, now: float) -> None:
        """End the session if the Edit light has been off too long (no frames needed)."""
        if self.session is not None and (self._edit_at is None or now - self._edit_at > self.EDIT_HOLD):
            self.end(now)

    def _on_label(self, label: Label, now: float) -> None:
        if self.session is None:
            self.session = _Session()
        s = self.session
        if label.menu is not None:
            s.menu = label.menu
        s.last_label = label.code
        s.last_label_at = now
        self.label = label
        self.value = None
        if label.value is not None:
            self._record(label.code, label.value)

    def _record(self, code: str, value) -> None:
        s = self.session
        s.first.setdefault(code, value)
        s.last[code] = value

    def end(self, now: float) -> None:
        s = self.session
        if s is None:
            return
        self.session, self.label, self.value = None, None, None
        saved = s.last_label == "SEnd" and now - s.last_label_at <= self.EDIT_HOLD + self.SAVE_WINDOW
        values = s.last if saved else s.first
        if values and self.on_commit is not None:
            self.on_commit(dict(values))
