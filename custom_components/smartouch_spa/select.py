"""Device keys with more than two states, as selects.

State comes from each key's Lo/Hi lights; choosing an option presses the key
until the lights match (SpaClient.press_to_state). Which keys get a select
depends on the spa's equipment (spa_core/equipment.py): a dual-speed pump is
Off / Low / High, and two single-speed AUX pumps are Off / Jets A / Jets B /
Both (the AUX key steps A, A+B, B, off; the Lo light is pump A).
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
from .spa_core.equipment import Jets1, Jets2
from .spa_core.protocol import Key

# option -> key state (from the Lo/Hi lights)
SPEEDS = {"off": "off", "low": "low", "high": "high"}
TWO_PUMPS = {"off": "off", "jets_a": "low", "jets_b": "high", "both": "low_high"}


def select_keys(equipment) -> dict[Key, tuple[str, dict[str, str]]]:
    """key -> (translation key, option map) for the keys this spa shows as selects."""
    out: dict[Key, tuple[str, dict[str, str]]] = {}
    if equipment.jets1 is Jets1.DUAL:
        out[Key.JETS] = ("jets", SPEEDS)
    if equipment.jets2 is Jets2.DUAL:
        out[Key.AUX2] = ("aux", SPEEDS)
    elif equipment.jets2 is Jets2.TWO:
        out[Key.AUX2] = ("jets2_pumps", TWO_PUMPS)
    return out


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = entry.runtime_data
    address = entry.data[CONF_ADDRESS]
    async_add_entities(
        KeySelect(client, address, key, tkey, options) for key, (tkey, options) in select_keys(client.equipment).items()
    )


class KeySelect(SpaEntity, SelectEntity):
    def __init__(self, client, address, key: Key, translation_key: str, options: dict[str, str]) -> None:
        super().__init__(client, address, f"select_{key.value}")
        self._key = key
        self._map = options
        self._attr_options = list(options)
        self._attr_translation_key = translation_key
        self._attr_icon = "mdi:pump"

    @property
    def current_option(self) -> str | None:
        state = self.client.key_state(self._key)
        for option, key_state in self._map.items():
            if key_state == state:
                return option
        return None

    @property
    def extra_state_attributes(self) -> dict:
        seen = self.client.observed_transitions.get(self._key.value, [])
        return {
            "lights": self.client.key_state(self._key),
            "observed_transitions": [f"{a} -> {b}" for a, b in seen[-8:]],
        }

    async def async_select_option(self, option: str) -> None:
        try:
            await self.client.press_to_state(self._key, self._map[option])
        except KeyCycleError as err:
            raise HomeAssistantError(str(err)) from err
        except Exception as err:
            raise HomeAssistantError(f"Press failed: {err}") from err
