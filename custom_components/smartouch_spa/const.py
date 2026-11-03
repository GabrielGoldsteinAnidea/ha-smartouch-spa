"""Constants for the SmarTouch Spa integration."""

from __future__ import annotations

DOMAIN = "smartouch_spa"

CONF_PIN = "pin"
CONF_MCODE = "mcode"  # this integration's own random app code, generated once per entry
CONF_SETPOINT_WINDOW = "setpoint_window"
CONF_TEMP_UNIT = "temp_unit"
CONF_SYNC_CLOCK = "sync_clock"
CONF_JETS1 = "jets1"
CONF_JETS2 = "jets2"
CONF_AIR = "air"

DEFAULT_SETPOINT_WINDOW = 5.0  # seconds; assumption, see spa_core/display.py
DEFAULT_TEMP_UNIT = "F"
DEFAULT_SYNC_CLOCK = False
DEFAULT_EQUIPMENT = "auto"  # from the P options captured off the panel

SERVICE_SEND_RAW = "send_raw"
SERVICE_PRESS = "press_button"
