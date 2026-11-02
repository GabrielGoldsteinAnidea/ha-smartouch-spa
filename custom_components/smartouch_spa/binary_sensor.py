"""Indicator LEDs from the display frame (names from the app's source)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import CONF_ADDRESS, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .entity import SpaEntity

# indicator -> (device class, enabled by default, diagnostic)
INDICATORS: dict[str, tuple[BinarySensorDeviceClass | None, bool, bool]] = {
    "heating": (BinarySensorDeviceClass.HEAT, True, False),
    "filtering": (BinarySensorDeviceClass.RUNNING, True, False),
    "overheat": (BinarySensorDeviceClass.PROBLEM, True, False),
    "jets_low": (BinarySensorDeviceClass.RUNNING, True, False),
    "jets_high": (BinarySensorDeviceClass.RUNNING, True, False),
    "jets2_low": (BinarySensorDeviceClass.RUNNING, False, False),
    "jets2_high": (BinarySensorDeviceClass.RUNNING, False, False),
    "air_low": (BinarySensorDeviceClass.RUNNING, False, False),
    "air_high": (BinarySensorDeviceClass.RUNNING, False, False),
    "edit": (None, False, True),
    "am": (None, False, True),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = entry.runtime_data
    address = entry.data[CONF_ADDRESS]
    async_add_entities(IndicatorSensor(client, address, name, *cfg) for name, cfg in INDICATORS.items())


class IndicatorSensor(SpaEntity, BinarySensorEntity):
    def __init__(self, client, address, name: str, device_class, enabled: bool, diagnostic: bool) -> None:
        super().__init__(client, address, f"led_{name}")
        self._led = name
        self._attr_translation_key = f"led_{name}"
        self._attr_device_class = device_class
        self._attr_entity_registry_enabled_default = enabled
        if diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool | None:
        return self.client.state.indicators.get(self._led)
