"""Parameter-menu durations (FP1d-FP4d, CLdn, ECL, CHCL, Uto, PUF).

Each shows the value Home Assistant will write at the next takeover of the
parameter menu (see SpaSettingEntity). Ranges are the manuals' (Programming
Manual pages 14-15); the step the panel uses is not known, so the takeover
checks every press and stops if a step skips over the value you chose.
"""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import CONF_ADDRESS, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .entity import SpaSettingEntity
from .spa_core import menus

UNITS = {"min": UnitOfTime.MINUTES, "s": UnitOfTime.SECONDS}


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = entry.runtime_data
    address = entry.data[CONF_ADDRESS]
    async_add_entities(SettingNumber(client, address, s) for s in menus.PARAMETERS if s.kind is menus.Kind.NUMBER)


class SettingNumber(SpaSettingEntity, NumberEntity):
    _attr_mode = NumberMode.BOX
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_step = 1
    _attr_icon = "mdi:timer-cog-outline"

    def __init__(self, client, address, setting) -> None:
        super().__init__(client, address, setting)
        self._attr_native_min_value = setting.min
        self._attr_native_max_value = setting.max
        self._attr_native_unit_of_measurement = UNITS[setting.unit]

    @property
    def native_value(self) -> float | None:
        value = self.desired_value
        return None if value is None else int(value)

    async def async_set_native_value(self, value: float) -> None:
        self.set_desired(int(value))
