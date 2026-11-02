"""Device keys as selects: state from each key's Lo/Hi lights, set by pressing the key.

Each device key on a SmarTouch panel steps through a fixed cycle (manual,
"Summary of functions for each device"): a dual-speed pump goes low, high,
off; a single-speed pump goes on, off; two single-speed AUX pumps go pump 1,
both, pump 2, off. Which cycle a spa has depends on how its controller is
configured, so this entity does not assume one. Choosing an option presses
the key and watches the lights until they match, and stops with an error if
the option is not in this spa's cycle (see SpaClient.press_to_state).

The options are named after the panel's "Lo" and "Hi" lights.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .client import KeyCycleError
from .entity import SpaEntity
from .spa_core.protocol import Key

OPTIONS = ["off", "low", "high", "low_high"]

# key -> (translation key, icon); "aux" is the Jets 2 select
KEYS: dict[Key, tuple[str, str]] = {
    Key.JETS: ("jets", "mdi:pump"),
    Key.AUX: ("air", "mdi:chart-bubble"),
    Key.AUX2: ("aux", "mdi:pump"),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = entry.runtime_data
    address = entry.data[CONF_ADDRESS]
    async_add_entities(KeySelect(client, address, key, *cfg) for key, cfg in KEYS.items())


class KeySelect(SpaEntity, SelectEntity):
    _attr_options = OPTIONS

    def __init__(self, client, address, key: Key, translation_key: str, icon: str) -> None:
        super().__init__(client, address, f"select_{key.value}")
        self._key = key
        self._attr_translation_key = translation_key
        self._attr_icon = icon

    @property
    def current_option(self) -> str | None:
        return self.client.key_state(self._key)

    @property
    def extra_state_attributes(self) -> dict:
        seen = self.client.observed_transitions.get(self._key.value, [])
        return {"observed_transitions": [f"{a} -> {b}" for a, b in seen[-8:]]}

    async def async_select_option(self, option: str) -> None:
        try:
            await self.client.press_to_state(self._key, option)
        except KeyCycleError as err:
            raise HomeAssistantError(str(err)) from err
        except Exception as err:
            raise HomeAssistantError(f"Press failed: {err}") from err
