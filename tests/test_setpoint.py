import asyncio

import pytest
from spa_core.setpoint import SetPointError, drive_set_point


class FakeSpa:
    """First press only reveals the set point (common panel behaviour)."""

    def __init__(self, sp, lo=80, hi=104, first_press_reveals=True):
        self.sp, self.lo, self.hi = sp, lo, hi
        self.revealed = not first_press_reveals
        self.presses = 0

    async def up(self):
        self.presses += 1
        if self.revealed:
            self.sp = min(self.hi, self.sp + 1)
        self.revealed = True

    async def down(self):
        self.presses += 1
        if self.revealed:
            self.sp = max(self.lo, self.sp - 1)
        self.revealed = True

    async def read(self):
        return self.sp


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("reveal", [True, False])
@pytest.mark.parametrize("start,target", [(100, 104), (104, 98), (101, 101)])
def test_reaches_target(start, target, reveal):
    spa = FakeSpa(start, first_press_reveals=reveal)
    res = run(drive_set_point(target, spa.up, spa.down, spa.read))
    assert res.final == target == spa.sp


def test_stall_at_limit():
    spa = FakeSpa(103)
    with pytest.raises(SetPointError, match="stuck"):
        run(drive_set_point(106, spa.up, spa.down, spa.read))


def test_timeout():
    spa = FakeSpa(100)

    async def none():
        return None

    with pytest.raises(SetPointError):
        run(drive_set_point(102, spa.up, spa.down, none))
