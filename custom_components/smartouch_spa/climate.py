"""Climate entity: water temperature, set point, and heating state."""

from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .const import CONF_TEMP_UNIT, DEFAULT_TEMP_UNIT
from .entity import SpaEntity
from .sensor import ha_unit
from .spa_core import protocol as p


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
    _attr_hvac_modes = [HVACMode.HEAT]  # noqa: RUF012
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    def __init__(self, client, address, key, unit: str) -> None:
        super().__init__(client, address, key)
        self._configured_unit = unit

    def _unit(self) -> str:
        """Return "F" or "C": the unit the spa displays, else the configured one."""
        st = self.client.state
        for reading in (st.water_temp, st.set_point):
            if reading is not None and reading.unit is not None:
                return reading.unit.value
        return self._configured_unit

    @property
    def temperature_unit(self) -> str:
        return ha_unit(None, self._unit())

    @property
    def min_temp(self) -> float:
        return p.APP_CELSIUS_VALUES[0] if self._unit() == "C" else p.TEMP_MIN_F

    @property
    def max_temp(self) -> float:
        return p.APP_CELSIUS_VALUES[-1] if self._unit() == "C" else p.TEMP_MAX_F

    @property
    def target_temperature_step(self) -> float:
        return 0.1 if self._unit() == "C" else 1

    @property
    def current_temperature(self) -> float | None:
        wt = self.client.state.water_temp
        return None if wt is None else wt.value

    def _target(self) -> tuple[float | None, str | None]:
        """Newest of: the set point read from the display, the set point we sent."""
        st = self.client.state
        cmd = self.client.commanded_set_point
        shown = st.set_point
        if shown is not None and (cmd is None or (st.last_set_point_at or 0) >= cmd[2]):
            return shown.value, "display"
        if cmd is not None and cmd[1] == self._unit():
            return cmd[0], "commanded"
        return None, None

    @property
    def target_temperature(self) -> float | None:
        return self._target()[0]

    @property
    def hvac_action(self) -> HVACAction | None:
        leds = self.client.state.indicators
        if "heating" not in leds:
            return None
        return HVACAction.HEATING if leds["heating"] else HVACAction.IDLE

    @property
    def extra_state_attributes(self) -> dict:
        return {"target_source": self._target()[1]}

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode != HVACMode.HEAT:
            raise HomeAssistantError("Only heat mode is supported")

    async def async_set_temperature(self, **kwargs) -> None:
        unit = self._unit()
        value = float(kwargs[ATTR_TEMPERATURE])
        value = p.nearest_app_celsius(value) if unit == "C" else round(value)
        try:
            await self.client.set_temperature(value, unit)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        except Exception as err:
            raise HomeAssistantError(f"Could not set temperature: {err}") from err
        self.async_write_ha_state()
