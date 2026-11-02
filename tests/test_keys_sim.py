"""Device-key cycling and clock writes against a simulated module.

The cycles are the ones the SmarTouch manual lists for each key setup
("Summary of functions for each device"). Which one a given spa uses is not
known in advance, which is what press_to_state has to cope with.
"""

import asyncio

import pytest

from .test_client_sim import PIN, SimModule, client_mod, make_client, p

LED_BITS = {name: p.INDICATOR_BITS[name] for pair in p.KEY_LEDS.values() for name in pair}
STATE_LEDS = {"off": (False, False), "low": (True, False), "high": (False, True), "low_high": (True, True)}

DUAL_SPEED = ["low", "high", "off"]  # JETS with a 2-speed pump: Low, High, Off
SINGLE_SPEED = ["high", "off"]  # 1-speed pump: only the high relay
TWO_AUX_PUMPS = ["low", "low_high", "high", "off"]  # AUX: P1, P1&2, P2, all off


class CyclingSim(SimModule):
    def __init__(self, cycles, stuck=()):
        super().__init__(pin=PIN)
        self.cycles = cycles  # key code -> list of states after each press
        self.pos = {code: len(c) - 1 for code, c in cycles.items()}  # start at "off"
        self.stuck = set(stuck)

    def key_state(self, code):
        return self.cycles[code][self.pos[code]] if code in self.cycles else "off"

    def frame(self):
        leds = bytearray(2)
        for key, (lo, hi) in p.KEY_LEDS.items():
            lo_on, hi_on = STATE_LEDS[self.key_state(p.KEY_CODES[key])]
            for name, on in ((lo, lo_on), (hi, hi_on)):
                if on:
                    byte, bit = LED_BITS[name]
                    leds[byte - 4] |= 1 << bit
        return p.encode_display(" 98F", dots=(False, False, False, True), leds=bytes(leds))

    async def write_gatt_char(self, uuid, data, response=False):
        text = bytes(data).decode()
        if uuid == p.CHAR_KEYBOARD and text in self.cycles and text not in self.stuck:
            self.writes.append((uuid, bytes(data)))
            self.pos[text] = (self.pos[text] + 1) % len(self.cycles[text])
            self._notify(p.CHAR_DISPLAY, self.frame())
            return
        await super().write_gatt_char(uuid, data, response)


def run(monkeypatch, sim, coro_fn):
    async def go():
        monkeypatch.setattr(client_mod, "KEY_SETTLE", 0)
        monkeypatch.setattr(client_mod, "KEY_RESPONSE_TIMEOUT", 0.2)
        c = make_client(monkeypatch, sim)
        await c.ensure_connected()
        await coro_fn(c)

    asyncio.run(go())


def presses(sim, code):
    return sum(1 for u, d in sim.writes if u == p.CHAR_KEYBOARD and d == code.encode())


def test_dual_speed_jets_reach_each_state(monkeypatch):
    sim = CyclingSim({"j0": DUAL_SPEED})

    async def body(c):
        assert c.key_state(p.Key.JETS) == "off"
        await c.press_to_state(p.Key.JETS, "high")
        assert c.key_state(p.Key.JETS) == "high" and presses(sim, "j0") == 2
        await c.press_to_state(p.Key.JETS, "high")  # already there: no press
        assert presses(sim, "j0") == 2
        await c.press_to_state(p.Key.JETS, "off")
        assert c.key_state(p.Key.JETS) == "off" and presses(sim, "j0") == 3
        assert c.observed_transitions["jets"] == [("off", "low"), ("low", "high"), ("high", "off")]

    run(monkeypatch, sim, body)


def test_two_aux_pumps_cycle(monkeypatch):
    sim = CyclingSim({"x0": TWO_AUX_PUMPS})

    async def body(c):
        await c.press_to_state(p.Key.AUX2, "high")  # pump 2 alone is the third press
        assert c.key_state(p.Key.AUX2) == "high" and presses(sim, "x0") == 3

    run(monkeypatch, sim, body)


def test_unreachable_state_stops_after_one_cycle(monkeypatch):
    sim = CyclingSim({"j0": SINGLE_SPEED})

    async def body(c):
        with pytest.raises(client_mod.KeyCycleError, match="not in this spa's cycle"):
            await c.press_to_state(p.Key.JETS, "low")
        # It went round once and stopped where it started.
        assert c.key_state(p.Key.JETS) == "off" and presses(sim, "j0") == 2

    run(monkeypatch, sim, body)


def test_no_light_change_stops_immediately(monkeypatch):
    sim = CyclingSim({"a0": DUAL_SPEED}, stuck={"a0"})

    async def body(c):
        with pytest.raises(client_mod.KeyCycleError, match="did not change"):
            await c.press_to_state(p.Key.AUX, "low")

    run(monkeypatch, sim, body)


def test_set_clock_writes_app_format(monkeypatch):
    sim = CyclingSim({})

    async def body(c):
        await c.set_clock(19, 45)
        assert (p.CHAR_TIME, b"0745P") in sim.writes
        assert c.commanded_clock[:2] == (19, 45)
        with pytest.raises(ValueError):
            await c.set_clock(25, 0)

    run(monkeypatch, sim, body)
