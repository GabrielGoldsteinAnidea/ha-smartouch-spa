"""Spa light: state from the light LED bit, toggled with the light key.

The LED bit (display byte 5, bit 4) and the key code ("l0") come from the
app's source. On the owner's spa the bit is set while the lamp is OFF, so
the state goes through protocol.lamp_on_from_indicators (docs/PROTOCOL.md).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .entity import SpaEntity
from .spa_core.protocol import Key, lamp_on_from_indicators


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([SpaLight(entry.runtime_data, entry.data[CONF_ADDRESS], "light")])


class SpaLight(SpaEntity, LightEntity):
    _attr_translation_key = "light"
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}  # noqa: RUF012

    @property
    def is_on(self) -> bool | None:
        return lamp_on_from_indicators(self.client.state.indicators)

    async def _toggle_to(self, on: bool) -> None:
        if self.is_on is None:
            raise HomeAssistantError("Light state is not known yet (no display frame received)")
        if self.is_on == on:
            return
        try:
            await self.client.press(Key.LIGHT)
        except Exception as err:
            raise HomeAssistantError(f"Press failed: {err}") from err

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._toggle_to(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._toggle_to(False)
