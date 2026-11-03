"""Menu takeover against a simulated panel.

The simulation follows the manuals' description of the menus (SET selects,
UP/DOWN scroll or change a value, SEnd saves) and the menu order read off the
owner's spa. How the real panel shows a value screen, and its step sizes,
are not known yet; these tests check that the takeover verifies every step
and stops when something does not match.
"""

import asyncio

import pytest

from .test_client_sim import PIN, SimModule, client_mod, make_client, p

menus = client_mod.menus  # the copy the client uses

EDIT_LED = 0x20
AM_LED = 0x80


class MenuSim(SimModule):
    def __init__(self, menu, start, values, up_forward=True, step=1):
        super().__init__(pin=PIN)
        self.menu = menu
        self.order = menus.ORDER[menu]
        self.idx = self.order.index(start)
        self.values = dict(values)  # code -> int or "HH:MM"
        self.saved = None
        self.up_forward = up_forward
        self.step = step
        self.editing = None  # None, "value", "hour", "minute"
        self.open = True

    def frame(self):
        if not self.open:
            return p.encode_display(" 98F", dots=(False, False, False, True))
        code = self.order[self.idx]
        st = menus.SETTINGS.get(code)
        leds = bytearray([0x01 | EDIT_LED, 0])
        if self.editing is None:
            if st is not None and st.kind is menus.Kind.FLAG:
                text = f"{code} {self.values[code]}"
            else:
                text = {"SEnd": "5End"}.get(code, code).ljust(4)
            return p.encode_display(text, leds=bytes(leds))
        value = self.values[code]
        if st.kind is menus.Kind.TIME:
            h, m = (int(x) for x in value.split(":"))
            if h < 12:
                leds[0] |= AM_LED
            return p.encode_display(f"{h % 12 or 12:2d}{m:02d}", dots=(False, True, True, False), leds=bytes(leds))
        return p.encode_display(f"{value:4d}", leds=bytes(leds))

    def key(self, code):
        cur = self.order[self.idx]
        st = menus.SETTINGS.get(cur)
        if code in ("u0", "d0"):
            sign = 1 if code == "u0" else -1
            if self.editing is None:
                self.idx = (self.idx + (sign if self.up_forward else -sign)) % len(self.order)
            elif self.editing == "value":
                self.values[cur] = max(st.min, min(st.max, self.values[cur] + sign * self.step))
            else:
                h, m = (int(x) for x in self.values[cur].split(":"))
                if self.editing == "hour":
                    h = (h + sign) % 24
                else:
                    m = (m + sign) % 60
                self.values[cur] = f"{h:02d}:{m:02d}"
        elif code == "s0":
            if self.editing is None:
                if cur == "SEnd":
                    self.saved, self.open = dict(self.values), False
                elif cur == "CAnC":
                    self.open = False
                elif st.kind is menus.Kind.FLAG:
                    self.values[cur] ^= 1
                else:
                    self.editing = "hour" if st.kind is menus.Kind.TIME else "value"
            elif self.editing == "hour":
                self.editing = "minute"
            else:
                self.editing = None
        self._notify(p.CHAR_DISPLAY, self.frame())

    async def write_gatt_char(self, uuid, data, response=False):
        text = bytes(data).decode()
        if uuid == p.CHAR_KEYBOARD and self.open:
            self.writes.append((uuid, bytes(data)))
            self.key(text)
            return
        await super().write_gatt_char(uuid, data, response)


def run(monkeypatch, sim, body):
    async def go():
        monkeypatch.setattr(client_mod, "MENU_CLOSE_TIMEOUT", 0.5)
        monkeypatch.setattr(client_mod, "MENU_RESPONSE_TIMEOUT", 0.3)
        monkeypatch.setattr(menus.MenuTracker, "EDIT_HOLD", 0.1)
        c = make_client(monkeypatch, sim)
        await c.ensure_connected()
        sim._notify(p.CHAR_DISPLAY, sim.frame())  # the operator has opened the menu
        await asyncio.sleep(0)
        await body(c)

    asyncio.run(go())


OPTION_VALUES = {**{f"U{i}": 0 for i in range(1, 9)}, **{f"P{i}": 0 for i in range(1, 9)}, "P2": 1, "P8": 1}
PARAM_VALUES = {
    "FP1": "00:00", "FP2": "00:00", "FP3": "00:00", "FP4": "00:00",
    "FP1d": 0, "FP2d": 0, "FP3d": 0, "FP4d": 0,
    "CLdn": 60, "ECL": 180, "CHCL": 60, "Uto": 20, "PUF": 60,
}  # fmt: skip


def test_options_takeover_saves_and_captures(monkeypatch):
    sim = MenuSim(menus.Menu.OPTIONS, "CAnC", OPTION_VALUES)

    async def body(c):
        done = await c.apply_settings({"U3": 1, "U1": 1, "P8": 0, "FP1d": 30})  # P8 protected, FP1d other menu
        assert done == ["U1", "U3"]
        assert sim.saved["U1"] == 1 and sim.saved["U3"] == 1 and sim.saved["P8"] == 1
        assert c.setting_value("U3") == 1  # captured on the way

    run(monkeypatch, sim, body)


def test_parameter_takeover_numbers_and_time(monkeypatch):
    sim = MenuSim(menus.Menu.PARAMETERS, "FP1", PARAM_VALUES, up_forward=False)

    async def body(c):
        done = await c.apply_settings({"FP1d": 5, "FP1": "20:15", "Uto": 18})
        assert done == ["FP1", "FP1d", "Uto"]
        assert sim.saved["FP1"] == "20:15" and sim.saved["FP1d"] == 5 and sim.saved["Uto"] == 18
        assert c.setting_value("FP1") == "20:15"

    run(monkeypatch, sim, body)


def test_step_that_skips_the_target_stops(monkeypatch):
    sim = MenuSim(menus.Menu.PARAMETERS, "FP1", PARAM_VALUES, step=10)

    async def body(c):
        with pytest.raises(client_mod.MenuError, match="jumped past"):
            await c.apply_settings({"FP1d": 15})
        assert sim.saved is None  # never reached SEnd

    run(monkeypatch, sim, body)


def test_refuses_without_open_menu(monkeypatch):
    sim = MenuSim(menus.Menu.OPTIONS, "U1", OPTION_VALUES)
    sim.open = False

    async def body(c):
        with pytest.raises(client_mod.MenuError, match="open the parameter or options menu"):
            await c.apply_settings({"U1": 1})
        assert not any(u == p.CHAR_KEYBOARD for u, _ in sim.writes)

    run(monkeypatch, sim, body)


def test_unexpected_menu_position_stops(monkeypatch):
    sim = MenuSim(menus.Menu.OPTIONS, "U1", OPTION_VALUES)

    async def body(c):
        real_key = sim.key

        def jumpy(code):
            if code in ("u0", "d0"):
                sim.idx = (sim.idx + 3) % len(sim.order)  # skips items
                sim._notify(p.CHAR_DISPLAY, sim.frame())
            else:
                real_key(code)

        sim.key = jumpy
        with pytest.raises(client_mod.MenuError, match="expected"):
            await c.apply_settings({"U6": 1})
        assert sim.saved is None

    run(monkeypatch, sim, body)


class DeadKeySim(MenuSim):
    """A panel that ignores some codes, like u0 on the owner's spa (2026-11-02)."""

    def __init__(self, *args, dead=("u0",), **kwargs):
        super().__init__(*args, **kwargs)
        self.dead = set(dead)

    def key(self, code):
        if code in self.dead:
            return  # nothing happens, no frame
        super().key(code)


def test_takeover_goes_round_with_down_only(monkeypatch):
    sim = DeadKeySim(menus.Menu.OPTIONS, "CAnC", OPTION_VALUES)

    async def body(c):
        done = await c.apply_settings({"U4": 1})
        assert done == ["U4"] and sim.saved["U4"] == 1
        assert p.MENU_UP in c.dead_menu_keys and p.MENU_DOWN not in c.dead_menu_keys
        assert any("u0 did not move" in line for line in c.menu_log)

    run(monkeypatch, sim, body)


def test_takeover_stops_when_no_key_moves(monkeypatch):
    sim = DeadKeySim(menus.Menu.OPTIONS, "CAnC", OPTION_VALUES, dead=("u0", "d0"))

    async def body(c):
        with pytest.raises(client_mod.MenuError, match="neither UP"):
            await c.apply_settings({"U4": 1})
        assert sim.saved is None

    run(monkeypatch, sim, body)
