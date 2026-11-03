"""Base entity."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .client import SpaClient
from .const import DOMAIN


class SpaEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, client: SpaClient, address: str, key: str) -> None:
        self.client = client
        self._attr_unique_id = f"{address}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            connections={(CONNECTION_BLUETOOTH, address)},
            manufacturer="Applied Computer Controls (ACC)",
            model="SmarTouch Digital / BWF-200",
            name="Spa",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.client.add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return self.client.authorized


class SpaSettingEntity(SpaEntity):
    """A controller setting from one of the panel's menus (spa_core/menus.py).

    The state is the value Home Assistant will write the next time it takes
    over that menu: a value changed here (pending) or else the value last
    read off the panel. Read-only settings only ever show the panel value.
    The data is stored locally, so these stay available when the spa is not
    connected.
    """

    def __init__(self, client: SpaClient, address: str, setting) -> None:
        super().__init__(client, address, f"setting_{setting.code}")
        self.setting = setting
        self._attr_name = f"{setting.name} ({setting.code})"
        self._attr_entity_category = EntityCategory.CONFIG if setting.writable else EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        return True

    @property
    def desired_value(self):
        if self.setting.code in self.client.pending_settings:
            return self.client.pending_settings[self.setting.code]
        return self.client.setting_value(self.setting.code)

    def set_desired(self, value) -> None:
        self.client.set_pending(self.setting.code, value)

    @property
    def extra_state_attributes(self) -> dict:
        entry = self.client.settings.get(self.setting.code)
        return {
            "code": self.setting.code,
            "menu": self.setting.menu.value,
            "spa_value": None if entry is None else entry["value"],
            "read_at": None if entry is None else datetime.fromtimestamp(entry["at"], UTC).isoformat(),
            "pending": self.setting.code in self.client.pending_settings,
        }
