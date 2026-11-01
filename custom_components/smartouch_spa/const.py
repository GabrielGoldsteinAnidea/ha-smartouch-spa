"""Constants for the SmarTouch Spa integration."""

from __future__ import annotations

from typing import Any

from .spa_core.profile import DEFAULT_PROFILE, Button, ProtocolProfile, parse_hex

DOMAIN = "smartouch_spa"

CONF_NOTIFY_UUID = "notify_uuid"
CONF_WRITE_UUID = "write_uuid"
CONF_WRITE_WITH_RESPONSE = "write_with_response"
CONF_DISPLAY_PREFIX = "display_prefix"
CONF_DISPLAY_OFFSET = "display_offset"
CONF_DISPLAY_LENGTH = "display_length"
CONF_SEGMENT_ORDER = "segment_order"
CONF_SETPOINT_WINDOW = "setpoint_window"
CONF_TEMP_UNIT = "temp_unit"
BUTTON_CONF_PREFIX = "button_"

DEFAULT_SETPOINT_WINDOW = 5.0  # seconds; assumption, see spa_core/display.py
DEFAULT_TEMP_UNIT = "F"
SETPOINT_READ_TIMEOUT = 4.0

SERVICE_SEND_RAW = "send_raw"
SERVICE_PRESS = "press_button"


def button_conf_key(button: Button) -> str:
    return f"{BUTTON_CONF_PREFIX}{button.value}"


def profile_from_options(options: dict[str, Any]) -> ProtocolProfile:
    """Build a profile from config entry options, falling back to defaults."""
    d = DEFAULT_PROFILE
    buttons = dict(d.buttons)
    for button in Button:
        raw = options.get(button_conf_key(button))
        if raw:
            buttons[button] = parse_hex(raw)
    prefix = options.get(CONF_DISPLAY_PREFIX)
    return ProtocolProfile(
        notify_uuid=options.get(CONF_NOTIFY_UUID) or d.notify_uuid,
        write_uuid=options.get(CONF_WRITE_UUID) or d.write_uuid,
        write_with_response=options.get(CONF_WRITE_WITH_RESPONSE, d.write_with_response),
        buttons=buttons,
        display_prefix=parse_hex(prefix) if prefix else d.display_prefix,
        display_offset=int(options.get(CONF_DISPLAY_OFFSET, d.display_offset)),
        display_length=int(options.get(CONF_DISPLAY_LENGTH, d.display_length)),
        segment_order=options.get(CONF_SEGMENT_ORDER) or d.segment_order,
    )
