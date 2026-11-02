"""BLE client for the SmarTouch BWF-200 module.

The connect sequence mirrors the app's bleconnected() (js/navigation.js):
subscribe to MMODE and DISPLAY, read VERSION, then write mcode + PIN to MCODE
and wait for MMODE to report the auth state. See docs/PROTOCOL.md for the
source of each step and for what is still unconfirmed on a real spa.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .spa_core import protocol as p
from .spa_core.display import DisplayTracker, SpaState

_LOGGER = logging.getLogger(__name__)

RAW_HISTORY = 200
AUTH_TIMEOUT = 8.0
AUTH_GRACE = 1.0
# The app waits 100 ms between subscriptions and 500 ms after connecting.
STEP_DELAY = 0.1
# After a key press, how long to wait for the indicator lights to change.
# The light LED changed 48 ms after "l0" on a real spa.
KEY_RESPONSE_TIMEOUT = 3.0
# Extra wait after the lights change, so a multi-step change settles.
KEY_SETTLE = 0.4
# A device key cycles through at most 4 states (manual, table 1).
MAX_CYCLE_PRESSES = 4


class KeyCycleError(Exception):
    """A device key did not reach the requested state."""


class SpaAuthError(Exception):
    """The module rejected the PIN (MMODE 'B') or is not set up yet ('F')."""

    def __init__(self, mmode: str) -> None:
        self.mmode = mmode
        reason = "the PIN was rejected" if mmode == p.MMode.PIN_REQUIRED else "the spa module is not set up"
        super().__init__(f"Authentication failed: {reason} (MMODE {mmode!r})")


@dataclass(frozen=True)
class RawFrame:
    at: float  # time.time()
    direction: str  # "rx" or "tx"
    uuid: str
    data: bytes

    def as_dict(self) -> dict:
        return {"at": self.at, "dir": self.direction, "uuid": self.uuid, "hex": self.data.hex(" ")}


class SpaClient:
    def __init__(self, ble_device: BLEDevice, mcode: str, pin: str, setpoint_window: float) -> None:
        self._device = ble_device
        self._auth = p.auth_writes(mcode, pin)  # validates the PIN
        self.tracker = DisplayTracker(setpoint_window=setpoint_window)
        self._client: BleakClientWithServiceCache | None = None
        self._connect_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []
        self._mmode_event = asyncio.Event()
        self._leds_changed = asyncio.Event()
        self._cycle_lock = asyncio.Lock()
        # key -> list of (from_state, to_state) transitions seen after presses
        self.observed_transitions: dict[str, list[tuple[str, str]]] = {}
        # (hour, minute, time.monotonic()) of the last clock this integration sent.
        self.commanded_clock: tuple[int, int, float] | None = None
        self.mmode: str | None = None
        self.version: dict | None = None
        # (value, unit, time.monotonic()) of the last set point this integration sent.
        self.commanded_set_point: tuple[float, str, float] | None = None
        self.raw_frames: deque[RawFrame] = deque(maxlen=RAW_HISTORY)
        self.gatt_table: list[dict] = []
        self.unique_payloads: dict[str, set[str]] = {}

    # ----------------------------------------------------------------- state
    @property
    def state(self) -> SpaState:
        return self.tracker.state

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    @property
    def authorized(self) -> bool:
        return self.connected and self.mmode in (p.MMode.MASTER, p.MMode.NORMAL)

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
            if self.authorized:
                return self._client
            if self._client is None or not self._client.is_connected:
                self._client = await establish_connection(
                    BleakClientWithServiceCache,
                    self._device,
                    self._device.name or self._device.address,
                    disconnected_callback=self._on_disconnect,
                )
            client = self._client
            try:
                await self._handshake(client)
            except Exception:
                await self.disconnect()
                raise
            self._notify_listeners()
            return client

    async def _handshake(self, client: BleakClientWithServiceCache) -> None:
        self._record_gatt_table(client)
        await client.start_notify(p.CHAR_MMODE, self._on_mmode)
        await asyncio.sleep(STEP_DELAY)
        await client.start_notify(p.CHAR_DISPLAY, self._on_display)
        await asyncio.sleep(STEP_DELAY)
        await self._read_version(client)
        # Anything MMODE said before the PIN write (e.g. 'B' on connect) is stale.
        self.mmode = None
        self._mmode_event.clear()
        async with self._write_lock:
            for chunk in self._auth:
                await client.write_gatt_char(p.CHAR_MCODE, chunk, response=p.WRITE_WITH_RESPONSE)
        # Never record the auth bytes: they contain the PIN.
        self._record("tx", p.CHAR_MCODE, b"<redacted>")
        if not await self._wait_mmode(AUTH_TIMEOUT):
            raise BleakError(f"no MMODE reply within {AUTH_TIMEOUT} s after sending the PIN")
        if self.mmode == p.MMode.PIN_REQUIRED:
            # A 'B' already in flight before the write may land first; give the real reply a moment.
            await self._wait_mmode(AUTH_GRACE)
        if self.mmode not in (p.MMode.MASTER, p.MMode.NORMAL):
            raise SpaAuthError(self.mmode or "")
        # The app reads the display once after authorising (prepare_main_page).
        try:
            self._handle_display(bytes(await client.read_gatt_char(p.CHAR_DISPLAY)))
        except BleakError as err:
            _LOGGER.debug("Initial display read failed: %s", err)

    async def _wait_mmode(self, timeout: float) -> bool:
        """Wait for the next MMODE notification. False on timeout."""
        try:
            await asyncio.wait_for(self._mmode_event.wait(), timeout)
        except TimeoutError:
            return False
        self._mmode_event.clear()
        return True

    async def _read_version(self, client: BleakClientWithServiceCache) -> None:
        try:
            raw = bytes(await client.read_gatt_char(p.CHAR_VERSION))
            self.version = json.loads(raw.decode("ascii", "replace"))
        except (BleakError, ValueError) as err:
            _LOGGER.debug("VERSION read failed: %s", err)

    async def disconnect(self) -> None:
        if self._client is not None:
            try:
                await self._client.disconnect()
            except BleakError:
                pass
        self._client = None
        self.mmode = None

    def _on_disconnect(self, _client) -> None:
        _LOGGER.debug("%s disconnected", self._device.address)
        self._client = None
        self.mmode = None
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
        _LOGGER.debug("GATT table for %s: %s", self._device.address, table)

    # ------------------------------------------------------------- receiving
    def _record(self, direction: str, uuid: str, data: bytes) -> None:
        self.raw_frames.append(RawFrame(time.time(), direction, uuid, bytes(data)))
        self.unique_payloads.setdefault(f"{direction} {uuid}", set()).add(bytes(data).hex(" "))
        _LOGGER.debug("%s %s %s", direction, uuid, bytes(data).hex(" "))

    def _on_mmode(self, char: BleakGATTCharacteristic, data: bytearray) -> None:
        self._record("rx", char.uuid, data)
        self.mmode = bytes(data).decode("ascii", "replace")[:1]
        self._mmode_event.set()
        self._notify_listeners()

    def _on_display(self, char: BleakGATTCharacteristic, data: bytearray) -> None:
        self._record("rx", char.uuid, data)
        self._handle_display(bytes(data))
        self._notify_listeners()

    def _handle_display(self, data: bytes) -> None:
        frame = p.parse_display(data)
        if frame is not None:
            if frame.indicators != self.tracker.state.indicators:
                self._leds_changed.set()
            self.tracker.update(frame.text, frame.indicators)

    # ------------------------------------------------------------ key state
    def key_state(self, key: p.Key) -> str | None:
        """State of a device key from its Lo/Hi lights: off, low, high or low_high."""
        lo_name, hi_name = p.KEY_LEDS[key]
        leds = self.state.indicators
        if lo_name not in leds:
            return None
        lo, hi = leds[lo_name], leds[hi_name]
        return {(False, False): "off", (True, False): "low", (False, True): "high", (True, True): "low_high"}[(lo, hi)]

    # --------------------------------------------------------------- sending
    async def _write(self, uuid: str, data: bytes) -> None:
        client = await self.ensure_connected()
        async with self._write_lock:
            await client.write_gatt_char(uuid, data, response=p.WRITE_WITH_RESPONSE)
        self._record("tx", uuid, data)
        self._notify_listeners()

    async def write_raw(self, uuid: str, data: bytes) -> None:
        """Raw write for reverse engineering. Refuses configuration characteristics."""
        if uuid.lower() in p.PROTECTED_CHARS:
            raise ValueError(f"writes to {uuid} change the module's configuration and are refused")
        await self._write(uuid.lower(), data)

    async def press(self, key: p.Key) -> None:
        await self._write(p.CHAR_KEYBOARD, p.encode_key(key))

    async def press_to_state(self, key: p.Key, target: str) -> None:
        """Press ``key`` until its lights show ``target``.

        Each press waits for the lights to change. It stops with KeyCycleError
        if a press changes nothing, or if the key comes back to a state it
        already showed (``target`` is not in this spa's cycle, or the heater
        is holding the low pump on). It never presses more than
        MAX_CYCLE_PRESSES times.
        """
        async with self._cycle_lock:
            current = self.key_state(key)
            if current is None:
                raise KeyCycleError("Key state is not known yet (no display frame received)")
            seen = [current]
            for _ in range(MAX_CYCLE_PRESSES):
                if current == target:
                    return
                self._leds_changed.clear()
                await self.press(key)
                try:
                    await asyncio.wait_for(self._leds_changed.wait(), KEY_RESPONSE_TIMEOUT)
                except TimeoutError:
                    raise KeyCycleError(
                        f"{key.value}: the lights did not change within {KEY_RESPONSE_TIMEOUT} s of a press"
                    ) from None
                await asyncio.sleep(KEY_SETTLE)
                new = self.key_state(key)
                self.observed_transitions.setdefault(key.value, []).append((current, new))
                self._notify_listeners()
                if new == current:
                    raise KeyCycleError(f"{key.value}: the press did not change the {key.value} lights")
                current = new
                if current == target:
                    return
                if current in seen:
                    raise KeyCycleError(
                        f"{key.value}: {target} is not in this spa's cycle (seen: {' -> '.join([*seen, current])})"
                    )
                seen.append(current)
            if current != target:
                raise KeyCycleError(f"{key.value}: did not reach {target} in {MAX_CYCLE_PRESSES} presses")

    async def set_clock(self, hour: int, minute: int) -> None:
        payload = p.encode_time(hour, minute)  # validates before anything is sent
        await self._write(p.CHAR_TIME, payload)
        self.commanded_clock = (hour, minute, time.monotonic())

    async def set_temperature(self, value: float, unit: str) -> None:
        payload = p.encode_temperature(value, unit)  # validates before anything is sent
        self.tracker.note_set_point_change()
        await self._write(p.CHAR_TEMPERATURE, payload)
        self.commanded_set_point = (value, unit, time.monotonic())
