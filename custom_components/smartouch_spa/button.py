"""Button entities: one press of each keypad key, plus clock sync.

Light has its own light entity and Jets, Air and Aux have selects that track
their state, but each key is also available as a plain press. The SET key
(the app calls it "system") tells the controller you are done using the spa:
per the manuals it turns everything off and starts post-use filtration, and
it acknowledges a high-limit (HLoH) error once the cause is fixed.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import SpaConfigEntry
from .client import MenuError
from .entity import SpaEntity
from .spa_core.protocol import Key

ICONS = {
    Key.JETS: "mdi:pump",
    Key.AUX: "mdi:chart-bubble",
    Key.AUX2: "mdi:pump",
    Key.SYSTEM: "mdi:check-circle-outline",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = entry.runtime_data
    address = entry.data[CONF_ADDRESS]
    async_add_entities(
        [
            *(SpaButton(client, address, k) for k in ICONS),
            SyncClockButton(client, address),
            ApplySettingsButton(client, address),
            DiscardSettingsButton(client, address),
        ]
    )


class SpaButton(SpaEntity, ButtonEntity):
    def __init__(self, client, address, key: Key) -> None:
        super().__init__(client, address, f"button_{key.value}")
        self._key = key
        self._attr_translation_key = key.value
        self._attr_icon = ICONS[key]

    async def async_press(self) -> None:
        try:
            await self.client.press(self._key)
        except Exception as err:
            raise HomeAssistantError(f"Press failed: {err}") from err


class SyncClockButton(SpaEntity, ButtonEntity):
    """Set the spa clock to Home Assistant's local time."""

    _attr_translation_key = "sync_clock"
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, client, address) -> None:
        super().__init__(client, address, "button_sync_clock")

    async def async_press(self) -> None:
        now = dt_util.now()
        try:
            await self.client.set_clock(now.hour, now.minute)
        except Exception as err:
            raise HomeAssistantError(f"Could not set the spa clock: {err}") from err


class ApplySettingsButton(SpaEntity, ButtonEntity):
    """Write pending settings through the menu someone has opened at the panel.

    The panel opens its menus only with two keys pressed together (SET+DOWN
    for parameters, UP+DOWN for options), which Bluetooth cannot send. Open
    the menu at the panel, then press this: Home Assistant steps to each
    pending item with UP/DOWN, sets it, and saves with SEnd. Every press is
    checked against the display; on any surprise it stops, and the panel
    discards unsaved changes after 60 s.
    """

    _attr_translation_key = "apply_settings"
    _attr_icon = "mdi:content-save-cog"

    def __init__(self, client, address) -> None:
        super().__init__(client, address, "button_apply_settings")

    async def async_press(self) -> None:
        try:
            await self.client.apply_settings(dict(self.client.pending_settings))
        except MenuError as err:
            raise HomeAssistantError(f"Takeover stopped: {err}") from err
        except Exception as err:
            raise HomeAssistantError(f"Takeover failed: {err}") from err


class DiscardSettingsButton(SpaEntity, ButtonEntity):
    """Forget settings changed in Home Assistant that were not written yet."""

    _attr_translation_key = "discard_settings"
    _attr_icon = "mdi:playlist-remove"

    def __init__(self, client, address) -> None:
        super().__init__(client, address, "button_discard_settings")

    @property
    def available(self) -> bool:
        return True

    async def async_press(self) -> None:
        for code in list(self.client.pending_settings):
            self.client.set_pending(code, None)
