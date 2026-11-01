"""Diagnostics download: GATT table + raw traffic, for protocol mapping."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from . import SpaConfigEntry


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: SpaConfigEntry) -> dict[str, Any]:
    client = entry.runtime_data
    st = client.state
    return {
        "options": dict(entry.options),
        "discovery_mode": client.discovery_mode,
        "connected": client.connected,
        "gatt_table": client.gatt_table,
        "state": {
            "display_text": st.display_text,
            "status_text": st.status_text,
            "water_temp": asdict(st.water_temp) if st.water_temp else None,
            "set_point": asdict(st.set_point) if st.set_point else None,
        },
        "unique_payloads": {k: sorted(v) for k, v in client.unique_payloads.items()},
        "raw_frames": [f.as_dict() for f in client.raw_frames],
    }
