"""Base entity."""

from __future__ import annotations

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
