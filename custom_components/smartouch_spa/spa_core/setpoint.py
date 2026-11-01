"""Closed-loop set point adjustment using only button presses + display.

The app (and therefore this integration) cannot write a set point directly;
it can only press Temp Up / Temp Down and observe the display. This module
drives the set point to a target by pressing a button, waiting for the
display to show the set point, and repeating.

The first press is not assumed to change the value: on many panels the first
press only reveals the current set point. The algorithm handles both cases
because it always reads the displayed value before deciding the next press.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass


class SetPointError(Exception):
    pass


@dataclass
class SetPointResult:
    final: int
    presses: int


async def drive_set_point(
    target: int,
    press_up: Callable[[], Awaitable[None]],
    press_down: Callable[[], Awaitable[None]],
    read_set_point: Callable[[], Awaitable[int | None]],
    *,
    max_presses: int = 60,
    max_stalls: int = 3,
) -> SetPointResult:
    """Step the set point towards ``target``.

    ``read_set_point`` must wait for the next set point shown after a press
    and return it, or ``None`` on timeout.
    """
    presses = 0
    await press_up()  # reveal (and possibly bump) the current set point
    presses += 1
    current = await read_set_point()
    if current is None:
        raise SetPointError("display did not show a set point after pressing Temp Up")

    stalls = 0
    while current != target:
        if presses >= max_presses:
            raise SetPointError(f"gave up after {presses} presses at {current}, target {target}")
        previous = current
        if current < target:
            await press_up()
        else:
            await press_down()
        presses += 1
        reading = await read_set_point()
        if reading is None:
            raise SetPointError("timed out waiting for set point display")
        current = reading
        if current == previous:
            stalls += 1
            if stalls >= max_stalls:
                # Reached a controller limit (e.g. max 104F) or presses are ignored.
                raise SetPointError(f"set point stuck at {current}; target {target} may be out of range")
        else:
            stalls = 0
    return SetPointResult(final=current, presses=presses)
