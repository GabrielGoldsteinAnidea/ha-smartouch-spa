"""Button entities for the keypad keys the app draws for a spa.

Light has its own light entity (state from the light LED), so it is not
repeated here. What System, Aux and Aux2 do on a given spa is not known yet,
so those are disabled by default.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .entity import SpaEntity
from .spa_core.protocol import Key

ICONS = {
    Key.JETS: "mdi:pump",
    Key.AUX: "mdi:numeric-1-box-outline",
    Key.AUX2: "mdi:numeric-2-box-outline",
    Key.SYSTEM: "mdi:cog",
}
DISABLED_BY_DEFAULT = {Key.AUX, Key.AUX2, Key.SYSTEM}


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = entry.runtime_data
    address = entry.data[CONF_ADDRESS]
    async_add_entities(SpaButton(client, address, k) for k in ICONS)


class SpaButton(SpaEntity, ButtonEntity):
    def __init__(self, client, address, key: Key) -> None:
        super().__init__(client, address, f"button_{key.value}")
        self._key = key
        self._attr_translation_key = key.value
        self._attr_icon = ICONS[key]
        self._attr_entity_registry_enabled_default = key not in DISABLED_BY_DEFAULT

    async def async_press(self) -> None:
        try:
            await self.client.press(self._key)
        except Exception as err:
            raise HomeAssistantError(f"Press failed: {err}") from err
