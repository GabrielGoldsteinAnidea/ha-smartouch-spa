"""On/off device keys as switches, and the panel's U options.

Device keys: a single-speed pump only uses the Hi light (manual: "only the
high pump will be activated"), and the air blower lights Air Hi. Turning a
switch on or off presses the key until the lights match.

U options: the switch shows the value Home Assistant will write the next time
it takes over the options menu (see button.ApplySettingsButton), which is
the value last read from the panel unless you changed it here.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .client import KeyCycleError
from .entity import SpaEntity, SpaSettingEntity
from .spa_core import menus
from .spa_core.equipment import Air, Jets1, Jets2
from .spa_core.protocol import Key


def switch_keys(equipment) -> dict[Key, str]:
    """key -> translation key for the keys this spa shows as on/off switches."""
    out: dict[Key, str] = {}
    if equipment.jets1 is Jets1.SINGLE:
        out[Key.JETS] = "jets"
    if equipment.jets2 is Jets2.SINGLE:
        out[Key.AUX2] = "aux"
    if equipment.air is Air.YES:
        out[Key.AUX] = "air"
    return out


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = entry.runtime_data
    address = entry.data[CONF_ADDRESS]
    entities: list[SwitchEntity] = [KeySwitch(client, address, k, t) for k, t in switch_keys(client.equipment).items()]
    entities += [
        OptionSwitch(client, address, s)
        for s in menus.OPTIONS
        if s.kind is menus.Kind.FLAG and s.code.startswith("U") and s.writable
    ]
    async_add_entities(entities)


class KeySwitch(SpaEntity, SwitchEntity):
    _attr_icon = "mdi:pump"

    def __init__(self, client, address, key: Key, translation_key: str) -> None:
        super().__init__(client, address, f"switch_{key.value}")
        self._key = key
        self._attr_translation_key = translation_key
        if key is Key.AUX:
            self._attr_icon = "mdi:chart-bubble"

    @property
    def is_on(self) -> bool | None:
        state = self.client.key_state(self._key)
        return None if state is None else state != "off"

    async def _go(self, state: str) -> None:
        try:
            await self.client.press_to_state(self._key, state)
        except KeyCycleError as err:
            raise HomeAssistantError(str(err)) from err
        except Exception as err:
            raise HomeAssistantError(f"Press failed: {err}") from err

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._go("high")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._go("off")


class OptionSwitch(SpaSettingEntity, SwitchEntity):
    _attr_icon = "mdi:tune-variant"

    @property
    def is_on(self) -> bool | None:
        value = self.desired_value
        return None if value is None else bool(int(value))

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.set_desired(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.set_desired(0)
