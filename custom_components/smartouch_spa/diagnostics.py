"""Diagnostics download: state, GATT table and raw traffic (PIN and codes redacted)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from . import SpaConfigEntry
from .const import CONF_MCODE, CONF_PIN

TO_REDACT = {CONF_PIN, CONF_MCODE, CONF_ADDRESS}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: SpaConfigEntry) -> dict[str, Any]:
    client = entry.runtime_data
    st = client.state
    return {
        "data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "connected": client.connected,
        "mmode": client.mmode,
        "version": client.version,
        "gatt_table": client.gatt_table,
        "state": {
            "display_text": st.display_text,
            "status_text": st.status_text,
            "indicators": st.indicators,
            "water_temp": asdict(st.water_temp) if st.water_temp else None,
            "set_point": asdict(st.set_point) if st.set_point else None,
            "commanded_set_point": client.commanded_set_point,
        },
        # The client never records MCODE contents, so these hold no PIN.
        "unique_payloads": {k: sorted(v) for k, v in client.unique_payloads.items()},
        "raw_frames": [f.as_dict() for f in client.raw_frames],
    }
