"""SpaClient against a simulated BWF-200 module (needs bleak + bleak-retry-connector).

The simulated module behaves the way the app's code expects (MMODE replies
'N' for the right PIN, 'B' otherwise). That behaviour is inferred from the
app, not observed; see docs/PROTOCOL.md.
"""

import asyncio
import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("bleak")
pytest.importorskip("bleak_retry_connector")

ROOT = Path(__file__).resolve().parents[1]
# Import the client without running the integration's __init__ (which needs
# Home Assistant's bluetooth component and its optional dependencies).
for name, path in (
    ("custom_components", ROOT / "custom_components"),
    ("custom_components.smartouch_spa", ROOT / "custom_components" / "smartouch_spa"),
):
    if name not in sys.modules:
        pkg = types.ModuleType(name)
        pkg.__path__ = [str(path)]
        sys.modules[name] = pkg
client_mod = importlib.import_module("custom_components.smartouch_spa.client")
p = importlib.import_module("custom_components.smartouch_spa.spa_core.protocol")

PIN = "4321"
MCODE = "ABCDEFGHIJKLMNOP"


class SimModule:
    """Fake BleakClient for the BWF-200."""

    def __init__(self, pin=PIN):
        self.is_connected = True
        self.pin = pin
        self.callbacks = {}
        self.writes = []
        self.auth_buf = ""
        self.light = False
        self.set_point = 100
        chars = [SimpleNamespace(uuid=u, handle=i, properties=["write"]) for i, u in enumerate([p.CHAR_DISPLAY])]
        self.services = [SimpleNamespace(uuid=p.SERVICE_UUID, characteristics=chars)]

    async def start_notify(self, uuid, cb):
        self.callbacks[uuid] = cb
        if uuid == p.CHAR_MMODE:
            self._notify(p.CHAR_MMODE, b"B")  # announces "PIN needed" before auth

    def _notify(self, uuid, data):
        cb = self.callbacks.get(uuid)
        if cb:
            asyncio.get_running_loop().call_soon(cb, SimpleNamespace(uuid=uuid), bytearray(data))

    def frame(self):
        leds = bytes([0b0000_0001, 0b0001_0000 if self.light else 0])
        return p.encode_display(" 98F", dots=(False, False, False, True), leds=leds)

    async def read_gatt_char(self, uuid):
        if uuid == p.CHAR_VERSION:
            return bytearray(b'{"ptype":0,"oem":"SmarTouch"}')
        if uuid == p.CHAR_DISPLAY:
            return bytearray(self.frame())
        raise AssertionError(uuid)

    async def write_gatt_char(self, uuid, data, response=False):
        assert response is True  # the app always writes with response
        self.writes.append((uuid, bytes(data)))
        text = bytes(data).decode()
        if uuid == p.CHAR_MCODE:
            flag, body = (text[0], text[1:]) if len(text) == 20 or text[0] == "9" else ("", text)
            self.auth_buf = body if flag == "0" else self.auth_buf + body
            if flag in ("", "9"):
                ok = self.auth_buf[-4:] == self.pin and len(self.auth_buf) == 20
                self._notify(p.CHAR_MMODE, b"N" if ok else b"B")
        elif uuid == p.CHAR_KEYBOARD and text == "l0":
            self.light = not self.light
            self._notify(p.CHAR_DISPLAY, self.frame())
        elif uuid == p.CHAR_TEMPERATURE:
            # The real module changes nothing on the display (2026-11-03).
            self.set_point = int(text[:3])

    async def disconnect(self):
        self.is_connected = False


def make_client(monkeypatch, sim):
    async def fake_establish(cls, device, name, disconnected_callback=None):
        return sim

    monkeypatch.setattr(client_mod, "establish_connection", fake_establish)
    monkeypatch.setattr(client_mod, "STEP_DELAY", 0)
    monkeypatch.setattr(client_mod, "AUTH_GRACE", 0.05)
    return client_mod.SpaClient(SimpleNamespace(address="AA:BB", name="spa"), MCODE, PIN, setpoint_window=5)


async def _happy(monkeypatch):
    sim = SimModule()
    c = make_client(monkeypatch, sim)
    await c.ensure_connected()
    assert c.authorized and c.mmode == "N"
    assert c.version == {"ptype": 0, "oem": "SmarTouch"}
    # Auth is mcode + PIN, chunked exactly like the app's splitter.
    assert [d for u, d in sim.writes if u == p.CHAR_MCODE] == [b"0" + MCODE.encode() + b"432", b"91"]
    # The PIN never reaches the recorded traffic.
    assert all(PIN.encode() not in f.data for f in c.raw_frames)
    assert c.state.water_temp.value == 98 and c.state.indicators["heating"]

    await c.press(p.Key.LIGHT)
    await asyncio.sleep(0)
    assert c.state.indicators["light"] is True

    await c.set_temperature(102, "F")
    await asyncio.sleep(0)
    assert (p.CHAR_TEMPERATURE, b"102F") in sim.writes
    assert sim.set_point == 102 and c.state.water_temp.value == 98
    assert c.commanded_set_point[:2] == (102, "F")

    with pytest.raises(ValueError):
        await c.set_temperature(110, "F")  # rejected before anything is sent
    with pytest.raises(ValueError):
        await c.write_raw(p.CHAR_MMODE, b"C")  # configuration commands are refused
    assert not any(u == p.CHAR_MMODE for u, _ in sim.writes)


def test_client_auth_and_control(monkeypatch):
    asyncio.run(_happy(monkeypatch))


async def _wrong_pin(monkeypatch):
    sim = SimModule(pin="0000")
    c = make_client(monkeypatch, sim)
    with pytest.raises(client_mod.SpaAuthError):
        await c.ensure_connected()
    assert not c.authorized and not sim.is_connected


def test_client_wrong_pin(monkeypatch):
    asyncio.run(_wrong_pin(monkeypatch))
