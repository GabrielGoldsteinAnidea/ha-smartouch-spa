"""Climate entity: water temperature + set point via button stepping."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .const import CONF_TEMP_UNIT, DEFAULT_TEMP_UNIT, SETPOINT_READ_TIMEOUT
from .entity import SpaEntity
from .sensor import ha_unit
from .spa_core.profile import Button
from .spa_core.setpoint import SetPointError, drive_set_point

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    unit = entry.options.get(CONF_TEMP_UNIT, DEFAULT_TEMP_UNIT)
    async_add_entities([SpaClimate(entry.runtime_data, entry.data[CONF_ADDRESS], "thermostat", unit)])


class SpaClimate(SpaEntity, ClimateEntity):
    _attr_translation_key = "thermostat"
    _attr_name = None  # use device name
    # The spa always heats to its set point; there is no off mode we can verify.
    _attr_hvac_mode = HVACMode.HEAT
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_target_temperature_step = 1

    def __init__(self, client, address, key, unit: str) -> None:
        super().__init__(client, address, key)
        self._unit = unit
        self._attr_hvac_modes = [HVACMode.HEAT]
        self._lock = asyncio.Lock()
        is_c = unit == "C"
        # Typical spa limits (assumption: 80-104F / 26-40C). Out-of-range
        # requests are also caught by stall detection in drive_set_point.
        self._attr_min_temp = 26 if is_c else 80
        self._attr_max_temp = 40 if is_c else 104

    @property
    def temperature_unit(self) -> str:
        wt = self.client.state.water_temp
        return ha_unit(wt.unit if wt else None, self._unit)

    @property
    def current_temperature(self) -> float | None:
        wt = self.client.state.water_temp
        return None if wt is None else wt.value

    @property
    def target_temperature(self) -> float | None:
        sp = self.client.state.set_point
        return None if sp is None else sp.value

    @property
    def available(self) -> bool:
        p = self.client.profile
        return super().available and p.can_read_display

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode != HVACMode.HEAT:
            raise HomeAssistantError("Only heat mode is supported")

    async def async_set_temperature(self, **kwargs) -> None:
        target = round(float(kwargs[ATTR_TEMPERATURE]))
        p = self.client.profile
        if not (p.can_press(Button.TEMP_UP) and p.can_press(Button.TEMP_DOWN)):
            raise HomeAssistantError("Temp Up/Down button payloads are not configured")

        async def read() -> int | None:
            return await self.client.wait_for_set_point(SETPOINT_READ_TIMEOUT)

        async with self._lock:
            try:
                result = await drive_set_point(
                    target,
                    lambda: self.client.press(Button.TEMP_UP),
                    lambda: self.client.press(Button.TEMP_DOWN),
                    read,
                )
            except SetPointError as err:
                raise HomeAssistantError(str(err)) from err
        _LOGGER.debug("Set point %s reached after %s presses", result.final, result.presses)
        self.async_write_ha_state()
