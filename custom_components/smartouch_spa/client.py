"""BLE client for the SmarTouch BWF-200 module.

The connect sequence mirrors the app's bleconnected() (js/navigation.js):
subscribe to MMODE and DISPLAY, read VERSION, then write mcode + PIN to MCODE
and wait for MMODE to report the auth state. See docs/PROTOCOL.md for the
source of each step and for what is still unconfirmed on a real spa.
"""

from __future__ import annotations

import asyncio
import itertools
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

from .spa_core import menus
from .spa_core import protocol as p
from .spa_core.display import DisplayTracker, SpaState

_LOGGER = logging.getLogger(__name__)

RAW_HISTORY = 1500
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
# How long to wait for the display to react to a key press inside a menu.
MENU_RESPONSE_TIMEOUT = 3.0
# How long to wait for the panel to close a menu after SET on SEnd.
MENU_CLOSE_TIMEOUT = 6.0
# The panel closed an untouched menu after about 30 s on the owner's spa, so
# a takeover has to start as soon as the menu opens: it can be armed ahead.
AUTO_TAKEOVER_ARM_TIME = 600.0


class KeyCycleError(Exception):
    """A device key did not reach the requested state."""


class MenuError(Exception):
    """A menu takeover stopped: the display did not show what was expected."""


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
        # Programming menus: passive capture of what the panel shows.
        self.menu = menus.MenuTracker(on_commit=self._on_menu_commit)
        # code -> {"value": ..., "at": time.time()} for every setting seen in a menu
        self.settings: dict[str, dict] = {}
        # code -> value the user wants written at the next menu takeover
        self.pending_settings: dict[str, int | str] = {}
        self.on_settings_changed: Callable[[], None] | None = None
        self.equipment = None  # spa_core.equipment.Equipment, set by the integration
        self._display_event = asyncio.Event()
        # (menu, key) -> +1 / -1: which way a key moves through a menu, learnt as it goes
        self._key_dir: dict[tuple[menus.Menu, bytes], int] = {}
        # UP/DOWN codes seen to do nothing in a menu on this panel
        self.dead_menu_keys: set[bytes] = set()
        self.menu_log: deque[str] = deque(maxlen=60)
        # time.monotonic() until which a menu opened at the panel is taken over at once
        self.auto_takeover_until: float | None = None
        self.last_takeover: dict | None = None  # {"at", "ok", "result"}
        self._takeover_task: asyncio.Task | None = None
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
            was_open = self.menu.open
            self.menu.update(frame.text, frame.indicators, time.monotonic())
            self._display_event.set()
            if self.menu.open and not was_open:
                self._maybe_auto_takeover()

    # ---------------------------------------------------------- auto takeover
    @property
    def auto_takeover_armed(self) -> bool:
        return self.auto_takeover_until is not None and time.monotonic() < self.auto_takeover_until

    def arm_auto_takeover(self, armed: bool) -> None:
        self.auto_takeover_until = time.monotonic() + AUTO_TAKEOVER_ARM_TIME if armed else None
        self._notify_listeners()

    def _maybe_auto_takeover(self) -> None:
        if not self.auto_takeover_armed or not self.pending_settings:
            return
        if self._takeover_task is not None and not self._takeover_task.done():
            return
        self.auto_takeover_until = None  # one attempt per arming
        self._takeover_task = asyncio.get_running_loop().create_task(self._auto_takeover())

    async def _auto_takeover(self) -> None:
        try:
            done = await self.apply_settings(dict(self.pending_settings))
            self.last_takeover = {"at": time.time(), "ok": True, "result": f"wrote {', '.join(done)}"}
        except Exception as err:  # reported through the entities, never raised
            _LOGGER.warning("Menu takeover stopped: %s (presses: %s)", err, list(self.menu_log))
            self.last_takeover = {"at": time.time(), "ok": False, "result": str(err)}
        self._notify_listeners()

    # ------------------------------------------------------------- settings
    def load_settings(self, stored: dict[str, dict]) -> None:
        self.settings = {k: v for k, v in stored.items() if k in menus.SETTINGS}

    def _on_menu_commit(self, values: dict) -> None:
        now = time.time()
        for code, value in values.items():
            self.settings[code] = {"value": value, "at": now}
            if self.pending_settings.get(code) == value:
                self.pending_settings.pop(code)  # the panel now has it
        self._settings_changed()

    def set_pending(self, code: str, value) -> None:
        if value is None or value == self.setting_value(code):
            self.pending_settings.pop(code, None)
        else:
            self.pending_settings[code] = value
        self._settings_changed()

    def _settings_changed(self) -> None:
        if self.on_settings_changed is not None:
            self.on_settings_changed()
        self._notify_listeners()

    def setting_value(self, code: str):
        entry = self.settings.get(code)
        return None if entry is None else entry["value"]

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
                before = current
                await self.press(key)
                # Wait for this key's own lights: other lights (Filtering) may be flashing.
                if not await self._wait_until(
                    lambda before=before: self.key_state(key) != before, KEY_RESPONSE_TIMEOUT
                ):
                    raise KeyCycleError(
                        f"{key.value}: the {key.value} lights did not change within {KEY_RESPONSE_TIMEOUT} s of a press"
                    )
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

    # ----------------------------------------------------------- menu takeover
    async def _wait_until(self, predicate, timeout: float) -> bool:
        """Wait for display frames until ``predicate()`` holds. False on timeout."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not predicate():
            remaining = deadline - loop.time()
            if remaining <= 0:
                return False
            self._display_event.clear()
            try:
                await asyncio.wait_for(self._display_event.wait(), remaining)
            except TimeoutError:
                self.menu.check_timeout(time.monotonic())
                return predicate()
        return True

    async def _wait_display(self, predicate, timeout: float, what: str) -> None:
        if not await self._wait_until(predicate, timeout):
            raise MenuError(f"timed out waiting for {what}")

    def _label_code(self) -> str | None:
        return None if self.menu.label is None else self.menu.label.code

    async def _menu_press(self, code: bytes) -> None:
        self.menu_log.append(f"press {code.decode()} at {self._label_code() or self.menu.value}")
        await self._write(p.CHAR_KEYBOARD, code)

    async def apply_settings(self, targets: dict[str, int | str]) -> list[str]:
        """Write ``targets`` through the menu someone has opened at the panel.

        Only writable settings of the open menu are applied. Each press must
        move the display exactly as expected, otherwise MenuError stops the
        takeover and no further key is pressed; the panel then discards the
        unsaved changes after 60 s without a key press (manuals). It ends with
        SET on SEnd. Returns the codes it wrote.
        """
        async with self._cycle_lock:
            if not self.menu.open or self.menu.label is None:
                raise MenuError("open the parameter or options menu at the spa panel first")
            if self.menu.on_value_screen:
                raise MenuError("press SET at the panel to return to the menu list first")
            self.menu_log.clear()
            menu = self.menu.menu or await self._identify_menu()
            order = menus.ORDER[menu]
            todo = {
                c: v
                for c, v in targets.items()
                if c in menus.SETTINGS and menus.SETTINGS[c].menu is menu and menus.SETTINGS[c].writable
            }
            for c, v in todo.items():
                st = menus.SETTINGS[c]
                if st.kind is menus.Kind.NUMBER and not (st.min <= int(v) <= st.max):
                    raise MenuError(f"{c} must be {st.min}-{st.max}")
            if not todo:
                raise MenuError(f"nothing to change in the {menu.value} menu")
            done = []
            for code in sorted(todo, key=order.index):
                await self._menu_goto(menu, code)
                await self._menu_set(code, todo[code])
                done.append(code)
            await self._menu_goto(menu, "SEnd")
            await self._menu_press(p.encode_key(p.Key.SYSTEM))
            await self._wait_display(lambda: not self.menu.open, MENU_CLOSE_TIMEOUT, "the menu to close after SEnd")
            return done

    def _alive_keys(self) -> list[bytes]:
        return [k for k in (p.MENU_UP, p.MENU_DOWN) if k not in self.dead_menu_keys]

    async def _menu_try(self, key: bytes, cur: str | None) -> bool:
        """Press ``key`` and wait for the menu to move off ``cur``. False if it did not move."""
        await self._menu_press(key)
        return await self._wait_until(
            lambda: self.menu.label is not None and self.menu.label.code != cur, MENU_RESPONSE_TIMEOUT
        )

    def _mark_dead(self, key: bytes, cur: str | None) -> None:
        # On the owner's spa u0 did not move the options menu (2026-11-02).
        self.dead_menu_keys.add(key)
        self.menu_log.append(f"{key.decode()} did not move the menu off {cur}")
        if not self._alive_keys():
            raise MenuError("neither UP (u0) nor DOWN (d0) moves the menu on this panel")

    async def _identify_menu(self) -> menus.Menu:
        """The menu opened on SEnd or CAnC, which both menus have: step until it shows."""
        trail = [self._label_code()]
        used: bytes | None = None
        for _ in range(5):
            alive = self._alive_keys()
            if not alive:
                break
            key = used if used in alive else alive[0]
            if not await self._menu_try(key, trail[-1]):
                self._mark_dead(key, trail[-1])
                continue
            used = key
            trail.append(self._label_code())
            menu = self.menu.label.menu
            if menu is None:
                continue
            order = menus.ORDER[menu]
            idx = [order.index(c) for c in trail]
            steps = {(b - a) % len(order) for a, b in itertools.pairwise(idx)}
            if steps == {1}:
                self._key_dir[(menu, key)] = 1
            elif steps == {len(order) - 1}:
                self._key_dir[(menu, key)] = -1
            else:
                raise MenuError(f"{key.decode()} moved {' -> '.join(trail)}, which fits neither menu")
            return menu
        raise MenuError(f"could not tell which menu is open ({' -> '.join(map(str, trail))})")

    async def _menu_goto(self, menu: menus.Menu, target: str) -> None:
        """Step to ``target``. Uses whichever of UP/DOWN moves the menu; the menu is circular."""
        order = menus.ORDER[menu]
        n = len(order)
        for _ in range(2 * n + 2):
            cur = self._label_code()
            if cur is None:
                raise MenuError("lost track of the menu")
            if cur == target:
                return
            want = 1 if (order.index(target) - order.index(cur)) % n <= n // 2 else -1
            alive = self._alive_keys()
            known = [k for k in alive if self._key_dir.get((menu, k)) == want]
            unknown = [k for k in alive if (menu, k) not in self._key_dir]
            key = (known or unknown or alive)[0]
            if not await self._menu_try(key, cur):
                self._mark_dead(key, cur)
                continue
            new = self._label_code()
            nxt, prv = menus.neighbours(menu, cur)
            if new == nxt:
                moved = 1
            elif new == prv:
                moved = -1
            else:
                raise MenuError(f"{key.decode()} moved from {cur} to {new}, expected {nxt} or {prv}")
            seen = self._key_dir.get((menu, key))
            if seen is not None and seen != moved:
                raise MenuError(f"{key.decode()} moved the other way this time ({cur} -> {new})")
            self._key_dir[(menu, key)] = moved
        raise MenuError(f"could not reach {target}")

    async def _menu_set(self, code: str, target) -> None:
        st = menus.SETTINGS[code]
        set_key = p.encode_key(p.Key.SYSTEM)
        if st.kind is menus.Kind.FLAG:
            if self.menu.label.value == int(target):
                return
            await self._menu_press(set_key)
            await self._wait_display(
                lambda: (
                    self.menu.label is not None
                    and self.menu.label.code == code
                    and self.menu.label.value == int(target)
                ),
                MENU_RESPONSE_TIMEOUT,
                f"{code} to show {target}",
            )
            return
        await self._menu_press(set_key)
        await self._wait_display(lambda: self.menu.on_value_screen, MENU_RESPONSE_TIMEOUT, f"the {code} value")
        if st.kind is menus.Kind.NUMBER:
            await self._menu_adjust(code, lambda v: v, int(target), None)
        else:
            hour, minute = (int(x) for x in str(target).split(":"))
            await self._menu_adjust(code, lambda v: int(v[:2]), hour, 24)
            await self._menu_press(set_key)  # hours locked in, minutes next
            await asyncio.sleep(0.3)
            await self._menu_adjust(code, lambda v: int(v[3:]), minute, 60)
        await self._menu_press(set_key)
        await self._wait_display(
            lambda: self.menu.label is not None and self.menu.label.code == code and not self.menu.on_value_screen,
            MENU_RESPONSE_TIMEOUT,
            f"the menu to return to {code}",
        )
        seen = self.menu.session.last.get(code) if self.menu.session else None
        want = str(target) if st.kind is menus.Kind.TIME else int(target)
        if seen is not None and seen != want:
            raise MenuError(f"{code} shows {seen} after setting, expected {want}")

    async def _menu_adjust(self, code: str, part, target: int, modulo: int | None) -> None:
        """Press UP/DOWN until ``part(value) == target``.

        Assumes UP increases; if the first press goes the other way it swaps
        once. Stops if a press skips over the target (the step does not fit).
        """
        up_increases = True
        swapped = False
        for _ in range(260):
            value = part(self.menu.value)
            if value == target:
                return
            want_up = target > value if modulo is None else (target - value) % modulo <= modulo // 2
            key = p.MENU_UP if want_up == up_increases else p.MENU_DOWN
            if key in self.dead_menu_keys:
                raise MenuError(f"{code}: changing it needs {key.decode()}, which does not work on this panel")
            await self._menu_press(key)
            old = value
            await self._wait_display(
                lambda old=old: self.menu.value is not None and part(self.menu.value) != old,
                MENU_RESPONSE_TIMEOUT,
                f"{code} to change from {old}",
            )
            new = part(self.menu.value)
            moved_up = (new - old) % modulo <= modulo // 2 if modulo else new > old
            if moved_up != want_up:
                if swapped:
                    raise MenuError(f"{code} moved the wrong way ({old} -> {new})")
                up_increases, swapped = not up_increases, True
                continue
            swapped = True  # direction confirmed
            if modulo is None and (new - target) * (old - target) < 0:
                raise MenuError(f"{code} jumped past {target} ({old} -> {new}); its step does not fit")
        raise MenuError(f"{code} did not reach {target}")

    async def set_clock(self, hour: int, minute: int) -> None:
        payload = p.encode_time(hour, minute)  # validates before anything is sent
        await self._write(p.CHAR_TIME, payload)
        self.commanded_clock = (hour, minute, time.monotonic())

    async def set_temperature(self, value: float, unit: str) -> None:
        payload = p.encode_temperature(value, unit)  # validates before anything is sent
        # The display does not show the new set point after a TEMPERATURE write
        # (2026-11-03 21:27:27: nothing changed on it for 31 s), so readings
        # after a write are water temperature, not set point.
        await self._write(p.CHAR_TEMPERATURE, payload)
        self.commanded_set_point = (value, unit, time.monotonic())
        self._settings_changed()  # remembered across restarts
