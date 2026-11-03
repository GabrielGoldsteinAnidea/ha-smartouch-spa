"""Which pumps and blower a spa has, from the options menu or the user's choice.

The controller's protected options describe the equipment (Programming
Manual pages 19-20): P2 = 1 primary pump is single speed, P7 = 1 secondary
pump is dual speed, P8 = 1 two single-speed secondary pumps, P6 = 1 air
blower disabled. Those values are captured whenever someone scrolls the
options menu at the panel (spa_core/menus.py). The integration's options
can override each one, for example to hide an air blower that is enabled in
the controller but not fitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

AUTO = "auto"


class Jets1(StrEnum):
    SINGLE = "single"  # JETS key: on, off
    DUAL = "dual"  # JETS key: low, high, off


class Jets2(StrEnum):
    NONE = "none"
    SINGLE = "single"  # AUX key: on, off
    DUAL = "dual"  # AUX key: low, high, off
    TWO = "two"  # AUX key: pump A, A+B, pump B, off


class Air(StrEnum):
    YES = "yes"
    NO = "no"


@dataclass(frozen=True)
class Equipment:
    jets1: Jets1
    jets2: Jets2
    air: Air


def resolve(jets1: str, jets2: str, air: str, settings_value) -> Equipment:
    """Combine the user's choices with captured P options (``settings_value(code)``)."""

    def flag(code: str) -> int | None:
        value = settings_value(code)
        return None if value is None else int(value)

    if jets1 == AUTO:
        jets1 = Jets1.SINGLE if flag("P2") == 1 else Jets1.DUAL
    if jets2 == AUTO:
        if flag("P8") == 1:
            jets2 = Jets2.TWO
        elif flag("P7") == 1:
            jets2 = Jets2.DUAL
        else:
            jets2 = Jets2.SINGLE
    if air == AUTO:
        air = Air.NO if flag("P6") == 1 else Air.YES
    return Equipment(Jets1(jets1), Jets2(jets2), Air(air))
