"""Indicator lights from the display frame, plus economy mode and problem state.

Light names come from the app's source. Economy and Problem come from the
messages the panel shows instead of the temperature (spa_core/status.py).
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import CONF_ADDRESS, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .entity import SpaEntity, SpaSettingEntity
from .spa_core import menus

# indicator -> (device class, enabled by default, diagnostic)
INDICATORS: dict[str, tuple[BinarySensorDeviceClass | None, bool, bool]] = {
    "heating": (BinarySensorDeviceClass.HEAT, True, False),
    "filtering": (BinarySensorDeviceClass.RUNNING, True, False),
    "overheat": (BinarySensorDeviceClass.PROBLEM, True, False),
    "jets_low": (BinarySensorDeviceClass.RUNNING, True, False),
    "jets_high": (BinarySensorDeviceClass.RUNNING, True, False),
    "jets2_low": (BinarySensorDeviceClass.RUNNING, True, False),
    "jets2_high": (BinarySensorDeviceClass.RUNNING, True, False),
    "air_low": (BinarySensorDeviceClass.RUNNING, True, False),
    "air_high": (BinarySensorDeviceClass.RUNNING, True, False),
    "edit": (None, True, True),
    "am": (None, True, True),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = entry.runtime_data
    address = entry.data[CONF_ADDRESS]
    async_add_entities(
        [
            *(IndicatorSensor(client, address, name, *cfg) for name, cfg in INDICATORS.items()),
            EconomySensor(client, address, "economy"),
            ProblemSensor(client, address, "problem"),
            MenuOpenSensor(client, address, "menu_open"),
            *(FlagSensor(client, address, s) for s in menus.OPTIONS if s.kind is menus.Kind.FLAG and not s.writable),
        ]
    )


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


class EconomySensor(SpaEntity, BinarySensorEntity):
    """On while the panel is showing "ECon" (economy mode)."""

    _attr_translation_key = "economy"
    _attr_icon = "mdi:leaf"

    @property
    def is_on(self) -> bool:
        return any(m.code == "economy" for m in self.client.tracker.current_messages())


class ProblemSensor(SpaEntity, BinarySensorEntity):
    """On while the panel shows an error code or the overheat light is lit."""

    _attr_translation_key = "problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self) -> bool:
        return bool(self.client.tracker.current_errors()) or bool(self.client.state.indicators.get("overheat"))

    @property
    def extra_state_attributes(self) -> dict:
        errors = self.client.tracker.current_errors()
        return {"errors": [m.code for m in errors], "details": [m.description for m in errors]}


class MenuOpenSensor(SpaEntity, BinarySensorEntity):
    """On while someone has a programming menu open at the panel."""

    _attr_translation_key = "menu_open"
    _attr_icon = "mdi:menu-open"

    @property
    def is_on(self) -> bool:
        return self.client.menu.open

    @property
    def extra_state_attributes(self) -> dict:
        m = self.client.menu
        return {
            "menu": None if m.menu is None else m.menu.value,
            "item": None if m.label is None else m.label.code,
            "value": m.value,
        }


class FlagSensor(SpaSettingEntity, BinarySensorEntity):
    """Read-only U7/U8 and protected P options, as last read from the panel."""

    @property
    def is_on(self) -> bool | None:
        value = self.client.setting_value(self.setting.code)
        return None if value is None else bool(int(value))
