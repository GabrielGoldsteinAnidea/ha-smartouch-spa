"""The spa's time-of-day clock.

Reading: the panel shows the time for the first 10 seconds of each minute
once it has been set (manual, "Time Of Day"); the AM light gives AM/PM. The
value shown here is the last time read off the display, advanced by the time
elapsed since, or the last time this integration set.

Setting: written to the TIME characteristic in the app's own format (see
spa_core.protocol.encode_time). The manuals note the clock resets to 12:00 AM
after a power cut, and filtration and silence periods run on it.
"""

from __future__ import annotations

import time as _time
from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpaConfigEntry
from .entity import SpaEntity, SpaSettingEntity
from .spa_core import menus


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = entry.runtime_data
    address = entry.data[CONF_ADDRESS]
    async_add_entities(
        [
            SpaClock(client, address, "clock"),
            *(SettingTime(client, address, s) for s in menus.PARAMETERS if s.kind is menus.Kind.TIME),
        ]
    )


class SpaClock(SpaEntity, TimeEntity):
    _attr_translation_key = "clock"
    _attr_icon = "mdi:clock-outline"

    def _source(self) -> tuple[tuple[int, int] | None, str | None]:
        st = self.client.state
        cmd = self.client.commanded_clock
        if st.clock_at is not None and (cmd is None or st.clock_at >= cmd[2]):
            return self.client.tracker.estimated_clock(), "display"
        if cmd is not None:
            minutes = (cmd[0] * 60 + cmd[1] + int((_time.monotonic() - cmd[2]) // 60)) % (24 * 60)
            return (minutes // 60, minutes % 60), "commanded"
        return None, None

    @property
    def native_value(self) -> time | None:
        value, _ = self._source()
        return None if value is None else time(value[0], value[1])

    @property
    def extra_state_attributes(self) -> dict:
        return {"clock_source": self._source()[1]}

    async def async_set_value(self, value: time) -> None:
        try:
            await self.client.set_clock(value.hour, value.minute)
        except Exception as err:
            raise HomeAssistantError(f"Could not set the spa clock: {err}") from err
        self.async_write_ha_state()


class SettingTime(SpaSettingEntity, TimeEntity):
    """Filtration period start times FP1-FP4 (parameter menu)."""

    _attr_icon = "mdi:clock-start"

    @property
    def native_value(self) -> time | None:
        value = self.desired_value
        if value is None:
            return None
        hour, minute = (int(x) for x in str(value).split(":"))
        return time(hour, minute)

    async def async_set_value(self, value: time) -> None:
        self.set_desired(f"{value.hour:02d}:{value.minute:02d}")
