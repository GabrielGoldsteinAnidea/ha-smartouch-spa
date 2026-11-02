"""SmarTouch Spa (ACC SmarTouch Digital / BWF-200) integration."""

from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval

from .client import SpaAuthError, SpaClient
from .const import (
    CONF_MCODE,
    CONF_PIN,
    CONF_SETPOINT_WINDOW,
    DEFAULT_SETPOINT_WINDOW,
    DOMAIN,
    SERVICE_PRESS,
    SERVICE_SEND_RAW,
)
from .spa_core.protocol import Key

_LOGGER = logging.getLogger(__name__)

RECONNECT_INTERVAL = timedelta(seconds=30)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.LIGHT,
    Platform.SENSOR,
]

type SpaConfigEntry = ConfigEntry[SpaClient]


async def async_setup_entry(hass: HomeAssistant, entry: SpaConfigEntry) -> bool:
    address: str = entry.data[CONF_ADDRESS]
    ble_device = bluetooth.async_ble_device_from_address(hass, address.upper(), connectable=True)
    if ble_device is None:
        raise ConfigEntryNotReady(f"Could not find SmarTouch spa with address {address}")

    client = SpaClient(
        ble_device,
        entry.data[CONF_MCODE],
        entry.data[CONF_PIN],
        float(entry.options.get(CONF_SETPOINT_WINDOW, DEFAULT_SETPOINT_WINDOW)),
    )
    try:
        await client.ensure_connected()
    except SpaAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except Exception as err:  # bleak raises many exception types
        raise ConfigEntryNotReady(f"Unable to connect to {address}: {err}") from err

    @callback
    def _async_update_ble(service_info: bluetooth.BluetoothServiceInfoBleak, change) -> None:
        client.set_ble_device(service_info.device)

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _async_update_ble,
            bluetooth.BluetoothCallbackMatcher(address=address),
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
    )

    auth_rejected = False

    async def _async_reconnect(_now) -> None:
        nonlocal auth_rejected
        # After a rejection, stop resending the PIN until the user re-enters it
        # (reauth reloads the entry). Whether the module locks out repeated
        # wrong PINs is unknown.
        if client.authorized or auth_rejected:
            return
        try:
            await client.ensure_connected()
        except SpaAuthError as err:
            auth_rejected = True
            _LOGGER.warning("Spa %s rejected the PIN: %s", address, err)
            entry.async_start_reauth(hass)
        except Exception as err:
            _LOGGER.debug("Reconnect to %s failed: %s", address, err)

    entry.async_on_unload(async_track_time_interval(hass, _async_reconnect, RECONNECT_INTERVAL))
    entry.runtime_data = client
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_options))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SpaConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.disconnect()
    return unloaded


async def _async_reload_on_options(hass: HomeAssistant, entry: SpaConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _client_for(hass: HomeAssistant, entry_id: str | None) -> SpaClient:
    entries = [e for e in hass.config_entries.async_loaded_entries(DOMAIN)]
    if entry_id:
        entries = [e for e in entries if e.entry_id == entry_id]
    if len(entries) != 1:
        raise ServiceValidationError("Specify config_entry_id (zero or several spas match)")
    return entries[0].runtime_data


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SEND_RAW):
        return

    async def send_raw(call: ServiceCall) -> None:
        client = _client_for(hass, call.data.get("config_entry_id"))
        try:
            data = bytes.fromhex(call.data["data"].replace(" ", "").replace(":", ""))
        except ValueError as err:
            raise ServiceValidationError(f"Invalid hex: {err}") from err
        try:
            await client.write_raw(call.data["uuid"], data)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        except Exception as err:
            raise HomeAssistantError(f"Write failed: {err}") from err

    async def press_button(call: ServiceCall) -> None:
        client = _client_for(hass, call.data.get("config_entry_id"))
        try:
            await client.press(Key(call.data["button"]))
        except Exception as err:
            raise HomeAssistantError(f"Press failed: {err}") from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_RAW,
        send_raw,
        schema=vol.Schema(
            {
                vol.Optional("config_entry_id"): cv.string,
                vol.Required("uuid"): cv.string,
                vol.Required("data"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PRESS,
        press_button,
        schema=vol.Schema(
            {
                vol.Optional("config_entry_id"): cv.string,
                vol.Required("button"): vol.In([k.value for k in Key]),
            }
        ),
    )
