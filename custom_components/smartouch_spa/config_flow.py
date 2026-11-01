"""Config and options flow for SmarTouch Spa."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback

from .const import (
    CONF_DISPLAY_LENGTH,
    CONF_DISPLAY_OFFSET,
    CONF_DISPLAY_PREFIX,
    CONF_NOTIFY_UUID,
    CONF_SEGMENT_ORDER,
    CONF_SETPOINT_WINDOW,
    CONF_TEMP_UNIT,
    CONF_WRITE_UUID,
    CONF_WRITE_WITH_RESPONSE,
    DEFAULT_SETPOINT_WINDOW,
    DEFAULT_TEMP_UNIT,
    DOMAIN,
    button_conf_key,
)
from .spa_core.profile import Button, parse_hex
from .spa_core.seven_segment import SegmentMap


class SmartouchSpaConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, str] = {}
        self._discovery: BluetoothServiceInfoBleak | None = None

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name or discovery_info.address}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._discovery is not None
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovery.name or self._discovery.address,
                data={CONF_ADDRESS: self._discovery.address},
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._discovery.name or self._discovery.address},
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick any connectable BLE device.

        The module's advertised name/UUIDs are not known yet, so there is no
        automatic matcher in manifest.json; the user picks the spa from all
        nearby connectable devices (name shown when advertised).
        """
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=self._discovered.get(address, address),
                data={CONF_ADDRESS: address},
            )

        current = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address in current:
                continue
            self._discovered[info.address] = f"{info.name or 'unknown'} ({info.address}, RSSI {info.rssi})"
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(self._discovered)}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return SmartouchSpaOptionsFlow()


def _validate(user_input: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    hex_keys = [CONF_DISPLAY_PREFIX] + [button_conf_key(b) for b in Button]
    for key in hex_keys:
        if user_input.get(key):
            try:
                parse_hex(user_input[key])
            except ValueError:
                errors[key] = "invalid_hex"
    try:
        SegmentMap.from_order(user_input.get(CONF_SEGMENT_ORDER) or "abcdefg.")
    except ValueError:
        errors[CONF_SEGMENT_ORDER] = "invalid_segment_order"
    return errors


class SmartouchSpaOptionsFlow(OptionsFlow):
    """Protocol parameters, so findings can be tried without code changes."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                return self.async_create_entry(data=user_input)

        o = user_input or dict(self.config_entry.options)

        def opt_str(key: str) -> vol.Optional:
            return vol.Optional(key, description={"suggested_value": o.get(key, "")})

        schema: dict = {
            opt_str(CONF_NOTIFY_UUID): str,
            opt_str(CONF_WRITE_UUID): str,
            vol.Optional(CONF_WRITE_WITH_RESPONSE, default=o.get(CONF_WRITE_WITH_RESPONSE, False)): bool,
            opt_str(CONF_DISPLAY_PREFIX): str,
            vol.Optional(CONF_DISPLAY_OFFSET, default=o.get(CONF_DISPLAY_OFFSET, 0)): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=512)
            ),
            vol.Optional(CONF_DISPLAY_LENGTH, default=o.get(CONF_DISPLAY_LENGTH, 0)): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=16)
            ),
            vol.Optional(CONF_SEGMENT_ORDER, default=o.get(CONF_SEGMENT_ORDER, "abcdefg.")): str,
            vol.Optional(CONF_SETPOINT_WINDOW, default=o.get(CONF_SETPOINT_WINDOW, DEFAULT_SETPOINT_WINDOW)): vol.All(
                vol.Coerce(float), vol.Range(min=0.5, max=30)
            ),
            vol.Optional(CONF_TEMP_UNIT, default=o.get(CONF_TEMP_UNIT, DEFAULT_TEMP_UNIT)): vol.In(["F", "C"]),
        }
        for button in Button:
            schema[opt_str(button_conf_key(button))] = str
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema), errors=errors)
