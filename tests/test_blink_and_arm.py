"""Flashing lights and the armed menu takeover."""

import asyncio

from spa_core.display import DisplayTracker

from .test_client_sim import client_mod, make_client, p
from .test_keys_sim import TWO_AUX_PUMPS, CyclingSim
from .test_menu_takeover_sim import OPTION_VALUES, MenuSim, menus


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_flashing_filter_light_reads_steady_on():
    clk = Clock()
    tr = DisplayTracker(clock=clk)
    tr.update("104°F", {"filtering": False})
    assert tr.led("filtering") is False
    # The owner's spa: on ~0.3 s, off ~0.7 s.
    for _ in range(6):
        clk.t += 0.7
        tr.update("104°F", {"filtering": True})
        clk.t += 0.3
        tr.update("104°F", {"filtering": False})
    assert tr.led_flashing("filtering") and tr.led("filtering") is True
    clk.t += 11  # stopped flashing
    assert not tr.led_flashing("filtering") and tr.led("filtering") is False
    # A steady light turns off at once.
    tr.update("104°F", {"filtering": True})
    clk.t += 1
    tr.update("104°F", {"filtering": False})
    assert tr.led("filtering") is False


class FlashingSim(CyclingSim):
    """Jets 2 with two pumps, while the Filtering light flashes on every frame."""

    def __init__(self):
        super().__init__({"x0": TWO_AUX_PUMPS})
        self.blink = False

    def frame(self):
        data = bytearray(super().frame())
        self.blink = not self.blink
        if self.blink:
            data[4] |= 1 << 4  # filtering
        return bytes(data)

    async def write_gatt_char(self, uuid, data, response=False):
        if uuid == p.CHAR_KEYBOARD:
            # An unrelated frame (filter light toggling) arrives before the key takes effect.
            self._notify(p.CHAR_DISPLAY, self.frame())
        await super().write_gatt_char(uuid, data, response)


def test_key_press_ignores_other_flashing_lights(monkeypatch):
    sim = FlashingSim()

    async def go():
        monkeypatch.setattr(client_mod, "KEY_SETTLE", 0)
        c = make_client(monkeypatch, sim)
        await c.ensure_connected()
        await c.press_to_state(p.Key.AUX2, "high")
        assert c.key_state(p.Key.AUX2) == "high"

    asyncio.run(go())


def test_armed_takeover_runs_when_menu_opens(monkeypatch):
    sim = MenuSim(menus.Menu.OPTIONS, "CAnC", OPTION_VALUES)
    sim.open = False

    async def go():
        monkeypatch.setattr(client_mod, "MENU_CLOSE_TIMEOUT", 0.5)
        monkeypatch.setattr(client_mod, "MENU_RESPONSE_TIMEOUT", 0.3)
        monkeypatch.setattr(menus.MenuTracker, "EDIT_HOLD", 0.1)
        c = make_client(monkeypatch, sim)
        await c.ensure_connected()
        c.set_pending("U4", 1)
        c.arm_auto_takeover(True)
        assert c.auto_takeover_armed
        sim.open = True  # the operator presses UP+DOWN at the panel
        sim._notify(p.CHAR_DISPLAY, sim.frame())
        await asyncio.sleep(0.05)
        assert not c.auto_takeover_armed  # one attempt per arming
        await c._takeover_task
        assert c.last_takeover["ok"], c.last_takeover
        assert sim.saved["U4"] == 1 and c.setting_value("U4") == 1
        assert c.pending_settings == {}

    asyncio.run(go())
