"""Constants for the SmarTouch Spa integration."""

from __future__ import annotations

DOMAIN = "smartouch_spa"

CONF_PIN = "pin"
CONF_MCODE = "mcode"  # this integration's own random app code, generated once per entry
CONF_SETPOINT_WINDOW = "setpoint_window"
CONF_TEMP_UNIT = "temp_unit"
CONF_SYNC_CLOCK = "sync_clock"

DEFAULT_SETPOINT_WINDOW = 5.0  # seconds; assumption, see spa_core/display.py
DEFAULT_TEMP_UNIT = "F"
DEFAULT_SYNC_CLOCK = False

SERVICE_SEND_RAW = "send_raw"
SERVICE_PRESS = "press_button"
