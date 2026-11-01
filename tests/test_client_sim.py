"""SpaClient end-to-end against a simulated spa (needs homeassistant + bleak installed)."""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.smartouch_spa import client as client_mod
from custom_components.smartouch_spa.spa_core.profile import Button, ProtocolProfile
from custom_components.smartouch_spa.spa_core.setpoint import drive_set_point
from custom_components.smartouch_spa.spa_core.seven_segment import SevenSegmentDecoder

NOTIFY = "0000fff1-0000-1000-8000-00805f9b34fb"
WRITE = "0000fff2-0000-1000-8000-00805f9b34fb"
UP, DOWN = b"\x01", b"\x02"
ENC = SevenSegmentDecoder()


class SimSpa:
    """Fake BleakClient: display frame = A5 + 4 digit bytes."""

    def __init__(self, *args, **kwargs):
        self.is_connected = True
        self.sp, self.water, self.revealed = 100, 98, False
        self.cb = None
        char = SimpleNamespace(uuid=NOTIFY, handle=0x12, properties=["notify"])
        self.services = [SimpleNamespace(uuid="fff0", characteristics=[char])]
        self.char = char

    async def start_notify(self, uuid, cb):
        self.cb = cb

    async def write_gatt_char(self, uuid, data, response=False):
        assert uuid == WRITE
        if self.revealed:
            self.sp += 1 if data == UP else -1
        self.revealed = True
        # Panel shows the set point shortly after the press.
        asyncio.get_running_loop().call_later(0.01, self.show, f"{self.sp}F")

    def show(self, text):
        self.cb(self.char, bytearray(b"\xa5" + ENC.encode(text)))

    async def disconnect(self):
        self.is_connected = False


async def _scenario(monkeypatch):
    sim = SimSpa()

    async def fake_establish(cls, device, name, disconnected_callback=None):
        return sim

    monkeypatch.setattr(client_mod, "establish_connection", fake_establish)
    profile = ProtocolProfile(
        notify_uuid=NOTIFY,
        write_uuid=WRITE,
        buttons={Button.TEMP_UP: UP, Button.TEMP_DOWN: DOWN},
        display_prefix=b"\xa5",
        display_offset=1,
        display_length=4,
    )
    c = client_mod.SpaClient(SimpleNamespace(address="AA:BB", name="spa"), profile, setpoint_window=5)
    await c.ensure_connected()
    sim.show(" 98F")
    assert c.state.water_temp.value == 98 and c.state.set_point is None

    res = await drive_set_point(
        103,
        lambda: c.press(Button.TEMP_UP),
        lambda: c.press(Button.TEMP_DOWN),
        lambda: c.wait_for_set_point(1.0),
    )
    assert res.final == 103 == sim.sp
    assert c.state.water_temp.value == 98  # set point readings didn't overwrite water temp
    assert any(f.direction == "tx" for f in c.raw_frames)
    with pytest.raises(ValueError):
        await c.press(Button.LIGHT)  # not configured


def test_client_drives_set_point(monkeypatch):
    asyncio.run(_scenario(monkeypatch))
