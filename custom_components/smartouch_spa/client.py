"""BLE client for the SmarTouch BWF-200 module.

Two modes:
  * discovery mode (profile not configured): subscribe to *every*
    characteristic with notify/indicate, record raw frames, expose them via
    sensors/diagnostics/logs so the protocol can be mapped from within HA.
  * normal mode: subscribe to ``profile.notify_uuid``, decode the display,
    and press buttons by writing ``profile.buttons[...]`` to
    ``profile.write_uuid``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .spa_core.display import DisplayTracker, SpaState
from .spa_core.profile import Button, ProtocolProfile

_LOGGER = logging.getLogger(__name__)

RAW_HISTORY = 200


@dataclass(frozen=True)
class RawFrame:
    at: float  # time.time()
    direction: str  # "rx" or "tx"
    uuid: str
    data: bytes

    def as_dict(self) -> dict:
        return {"at": self.at, "dir": self.direction, "uuid": self.uuid, "hex": self.data.hex(" ")}


class SpaClient:
    def __init__(self, ble_device: BLEDevice, profile: ProtocolProfile, setpoint_window: float) -> None:
        self._device = ble_device
        self.profile = profile
        self._decoder = profile.decoder()
        self.tracker = DisplayTracker(setpoint_window=setpoint_window)
        self._client: BleakClientWithServiceCache | None = None
        self._connect_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []
        self._setpoint_event = asyncio.Event()
        self.raw_frames: deque[RawFrame] = deque(maxlen=RAW_HISTORY)
        self.gatt_table: list[dict] = []
        self.unique_payloads: dict[str, set[str]] = {}

    # ----------------------------------------------------------------- state
    @property
    def discovery_mode(self) -> bool:
        return not self.profile.can_read_display

    @property
    def state(self) -> SpaState:
        return self.tracker.state

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        self._device = ble_device

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    def _notify_listeners(self) -> None:
        for cb in list(self._listeners):
            cb()

    # ------------------------------------------------------------ connection
    async def ensure_connected(self) -> BleakClientWithServiceCache:
        async with self._connect_lock:
            if self._client is not None and self._client.is_connected:
                return self._client
            client = await establish_connection(
                BleakClientWithServiceCache,
                self._device,
                self._device.name or self._device.address,
                disconnected_callback=self._on_disconnect,
            )
            self._client = client
            self._record_gatt_table(client)
            await self._subscribe(client)
            self._notify_listeners()
            return client

    async def disconnect(self) -> None:
        if self._client is not None:
            try:
                await self._client.disconnect()
            except BleakError:
                pass
        self._client = None

    def _on_disconnect(self, _client) -> None:
        _LOGGER.debug("%s disconnected", self._device.address)
        self._client = None
        self._notify_listeners()

    def _record_gatt_table(self, client: BleakClientWithServiceCache) -> None:
        table = []
        for service in client.services:
            for char in service.characteristics:
                table.append(
                    {
                        "service": service.uuid,
                        "characteristic": char.uuid,
                        "handle": char.handle,
                        "properties": list(char.properties),
                    }
                )
        self.gatt_table = table
        _LOGGER.info("GATT table for %s: %s", self._device.address, table)

    async def _subscribe(self, client: BleakClientWithServiceCache) -> None:
        if not self.discovery_mode:
            await client.start_notify(self.profile.notify_uuid, self._on_notify)
            return
        # Discovery mode: subscribe to everything that can notify.
        for service in client.services:
            for char in service.characteristics:
                if {"notify", "indicate"} & set(char.properties):
                    try:
                        await client.start_notify(char, self._on_notify)
                        _LOGGER.info("Discovery: subscribed to %s", char.uuid)
                    except BleakError as err:
                        _LOGGER.warning("Discovery: cannot subscribe to %s: %s", char.uuid, err)

    # ------------------------------------------------------------- receiving
    def _record(self, direction: str, uuid: str, data: bytes) -> None:
        self.raw_frames.append(RawFrame(time.time(), direction, uuid, bytes(data)))
        self.unique_payloads.setdefault(f"{direction} {uuid}", set()).add(bytes(data).hex(" "))
        _LOGGER.debug("%s %s %s", direction, uuid, bytes(data).hex(" "))

    def _on_notify(self, char: BleakGATTCharacteristic, data: bytearray) -> None:
        self._record("rx", char.uuid, data)
        digits = self.profile.extract_display(bytes(data))
        if digits is not None:
            text = self._decoder.decode(digits)
            had_setpoint_at = self.state.last_set_point_at
            self.tracker.update(text)
            if self.state.last_set_point_at != had_setpoint_at:
                self._setpoint_event.set()
        self._notify_listeners()

    # --------------------------------------------------------------- sending
    async def write_raw(self, uuid: str, data: bytes, response: bool | None = None) -> None:
        client = await self.ensure_connected()
        if response is None:
            response = self.profile.write_with_response
        async with self._write_lock:
            await client.write_gatt_char(uuid, data, response=response)
        self._record("tx", uuid, data)
        self._notify_listeners()

    async def press(self, button: Button) -> None:
        if not self.profile.can_press(button):
            raise ValueError(f"button {button.value} is not configured (see integration options)")
        if button in (Button.TEMP_UP, Button.TEMP_DOWN):
            # Clear before writing so a reply arriving immediately is not missed.
            self._setpoint_event.clear()
            self.tracker.note_temp_button_press()
        await self.write_raw(self.profile.write_uuid, self.profile.buttons[button])

    async def wait_for_set_point(self, timeout: float) -> int | None:
        """Wait for the first set point reading since the last temp button press."""
        try:
            await asyncio.wait_for(self._setpoint_event.wait(), timeout)
        except TimeoutError:
            return None
        sp = self.state.set_point
        return None if sp is None else sp.value
