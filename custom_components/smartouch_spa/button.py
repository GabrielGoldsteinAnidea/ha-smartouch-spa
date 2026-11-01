"""Button entities: one per keypad button.

Buttons (not switches/lights) are used deliberately: the app only sends
key presses, and whether light/filter on-off state can be read back from the
display/indicator data is not known yet. Exposing a switch without real state
feedback would report state we cannot verify.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .entity import SpaEntity
from .spa_core.profile import Button

ICONS = {
    Button.TEMP_UP: "mdi:thermometer-chevron-up",
    Button.TEMP_DOWN: "mdi:thermometer-chevron-down",
    Button.LIGHT: "mdi:lightbulb",
    Button.FILTER: "mdi:air-filter",
    Button.JETS: "mdi:pump",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = entry.runtime_data
    address = entry.data[CONF_ADDRESS]
    async_add_entities(SpaButton(client, address, b) for b in Button)


class SpaButton(SpaEntity, ButtonEntity):
    def __init__(self, client, address, button: Button) -> None:
        super().__init__(client, address, f"button_{button.value}")
        self._button = button
        self._attr_translation_key = button.value
        self._attr_icon = ICONS[button]

    @property
    def available(self) -> bool:
        return super().available and self.client.profile.can_press(self._button)

    async def async_press(self) -> None:
        await self.client.press(self._button)
