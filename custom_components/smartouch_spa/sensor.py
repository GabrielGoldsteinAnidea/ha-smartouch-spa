"""Sensors: decoded display, water temperature, raw traffic (diagnostic)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import CONF_ADDRESS, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .const import CONF_TEMP_UNIT, DEFAULT_TEMP_UNIT
from .entity import SpaEntity
from .spa_core.display import Unit


def ha_unit(reading_unit: Unit | None, configured: str) -> str:
    unit = reading_unit.value if reading_unit else configured
    return UnitOfTemperature.CELSIUS if unit == "C" else UnitOfTemperature.FAHRENHEIT


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = entry.runtime_data
    address = entry.data[CONF_ADDRESS]
    unit = entry.options.get(CONF_TEMP_UNIT, DEFAULT_TEMP_UNIT)
    async_add_entities(
        [
            DisplaySensor(client, address, "display"),
            WaterTempSensor(client, address, "water_temperature", unit),
            LastFrameSensor(client, address, "last_frame"),
        ]
    )


class DisplaySensor(SpaEntity, SensorEntity):
    _attr_translation_key = "display"
    _attr_icon = "mdi:numeric"

    @property
    def native_value(self) -> str | None:
        return self.client.state.display_text

    @property
    def extra_state_attributes(self) -> dict:
        st = self.client.state
        return {"status_text": st.status_text, "discovery_mode": self.client.discovery_mode}


class WaterTempSensor(SpaEntity, SensorEntity):
    _attr_translation_key = "water_temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, client, address, key, unit: str) -> None:
        super().__init__(client, address, key)
        self._unit = unit

    @property
    def native_value(self) -> int | None:
        wt = self.client.state.water_temp
        return None if wt is None else wt.value

    @property
    def native_unit_of_measurement(self) -> str:
        wt = self.client.state.water_temp
        return ha_unit(wt.unit if wt else None, self._unit)


class LastFrameSensor(SpaEntity, SensorEntity):
    """Most recent raw BLE frame. Primary reverse-engineering aid."""

    _attr_translation_key = "last_frame"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:bluetooth-transfer"

    @property
    def native_value(self) -> str | None:
        if not self.client.raw_frames:
            return None
        f = self.client.raw_frames[-1]
        # State is limited to 255 chars.
        return f"{f.direction} {f.data.hex(' ')}"[:255]

    @property
    def extra_state_attributes(self) -> dict:
        if not self.client.raw_frames:
            return {}
        f = self.client.raw_frames[-1]
        return {"uuid": f.uuid, "length": len(f.data), "frames_seen": len(self.client.raw_frames)}
