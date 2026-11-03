"""Config, reauth and options flow for SmarTouch Spa."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode

from .const import (
    CONF_AIR,
    CONF_JETS1,
    CONF_JETS2,
    CONF_MCODE,
    CONF_PIN,
    CONF_SETPOINT_WINDOW,
    CONF_SYNC_CLOCK,
    CONF_TEMP_UNIT,
    DEFAULT_EQUIPMENT,
    DEFAULT_SETPOINT_WINDOW,
    DEFAULT_SYNC_CLOCK,
    DEFAULT_TEMP_UNIT,
    DOMAIN,
)
from .spa_core.protocol import SERVICE_UUID, generate_mcode

PIN_SCHEMA = vol.Schema({vol.Required(CONF_PIN): str})


def _choice(key: str, options: list[str]) -> SelectSelector:
    return SelectSelector(SelectSelectorConfig(options=options, translation_key=key, mode=SelectSelectorMode.DROPDOWN))


def _valid_pin(pin: str) -> bool:
    return len(pin) == 4 and pin.isdigit()


class SmartouchSpaConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, str] = {}
        self._address: str | None = None
        self._name: str | None = None

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._address = discovery_info.address
        self._name = discovery_info.name or discovery_info.address
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_pin()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick a nearby module.

        Devices advertising the SmarTouch service are listed. If none do (the
        advertisement has not been observed yet), all connectable devices are
        listed instead.
        """
        if user_input is not None:
            self._address = user_input[CONF_ADDRESS]
            self._name = self._discovered.get(self._address, self._address)
            await self.async_set_unique_id(self._address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return await self.async_step_pin()

        current = self._async_current_ids(include_ignore=False)
        infos = [i for i in async_discovered_service_info(self.hass, connectable=True) if i.address not in current]
        matching = [i for i in infos if SERVICE_UUID in (u.lower() for u in i.service_uuids)]
        for info in matching or infos:
            self._discovered[info.address] = f"{info.name or 'unknown'} ({info.address}, RSSI {info.rssi})"
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(self._discovered)}),
        )

    async def async_step_pin(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if _valid_pin(user_input[CONF_PIN]):
                return self.async_create_entry(
                    title=self._name or self._address,
                    data={
                        CONF_ADDRESS: self._address,
                        CONF_PIN: user_input[CONF_PIN],
                        # Our own app code, like the one each phone install generates.
                        CONF_MCODE: generate_mcode(),
                    },
                )
            errors[CONF_PIN] = "invalid_pin"
        return self.async_show_form(
            step_id="pin",
            data_schema=PIN_SCHEMA,
            errors=errors,
            description_placeholders={"name": self._name or ""},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if _valid_pin(user_input[CONF_PIN]):
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_PIN: user_input[CONF_PIN]}
                )
            errors[CONF_PIN] = "invalid_pin"
        return self.async_show_form(step_id="reauth_confirm", data_schema=PIN_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return SmartouchSpaOptionsFlow()


class SmartouchSpaOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        o = dict(self.config_entry.options)
        schema = vol.Schema(
            {
                vol.Optional(CONF_TEMP_UNIT, default=o.get(CONF_TEMP_UNIT, DEFAULT_TEMP_UNIT)): vol.In(["F", "C"]),
                vol.Optional(
                    CONF_SETPOINT_WINDOW, default=o.get(CONF_SETPOINT_WINDOW, DEFAULT_SETPOINT_WINDOW)
                ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=30)),
                vol.Optional(CONF_SYNC_CLOCK, default=o.get(CONF_SYNC_CLOCK, DEFAULT_SYNC_CLOCK)): bool,
                vol.Optional(CONF_JETS1, default=o.get(CONF_JETS1, DEFAULT_EQUIPMENT)): _choice(
                    CONF_JETS1, ["auto", "single", "dual"]
                ),
                vol.Optional(CONF_JETS2, default=o.get(CONF_JETS2, DEFAULT_EQUIPMENT)): _choice(
                    CONF_JETS2, ["auto", "none", "single", "dual", "two"]
                ),
                vol.Optional(CONF_AIR, default=o.get(CONF_AIR, DEFAULT_EQUIPMENT)): _choice(
                    CONF_AIR, ["auto", "yes", "no"]
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
