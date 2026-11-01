# SmarTouch Spa for Home Assistant

A Home Assistant custom integration for spas that use the ACC (Applied
Computer Controls) **SmarTouch Digital** control with the **BWF-200**
WiFi/Bluetooth module, which is the hardware behind the "SmarTouch Digital"
phone app. The repo also includes the tooling to reverse-engineer the app's
protocol.

> **Status: protocol not yet mapped.** The integration is complete apart from
> the protocol constants: the characteristic UUIDs, the frame layout and the
> button payloads. Until those are known, it runs in **discovery mode**,
> where it captures raw BLE traffic for mapping. See
> [docs/PROTOCOL.md](docs/PROTOCOL.md) for what is known and what is not, and
> [docs/REVERSE_ENGINEERING.md](docs/REVERSE_ENGINEERING.md) for the capture
> procedure.

## How it works

The app does not read spa state directly. It mirrors the keypad: it sends
button presses and shows the keypad's 7-segment display. This integration
does the same:

* **Display → state.** Display frames are decoded from 7-segment bytes into
  text (`spa_core/seven_segment.py`). Temperatures shown within a few
  seconds of a temp button press are treated as the **set point**. All other
  temperatures are treated as **water temperature** (`spa_core/display.py`).
* **Set temperature = closed loop.** To set the temperature, the integration
  presses Temp Up/Down, reads the set point from the display, and repeats
  until it matches the target. It stops when the value stalls, for example
  at the controller's limit (`spa_core/setpoint.py`).
* **Buttons, not switches.** Light, Filter and Jets are exposed as buttons.
  Whether their on/off state can be read from the display data is not known
  yet, and a switch without state feedback would report state we can't
  verify.

### Entities

| Entity | Notes |
|---|---|
| `climate` Thermostat | Current temperature, plus a target temperature driven by button stepping. Available once the display is mapped. |
| `sensor` Water temperature | |
| `sensor` Display | The raw display text, such as `102F` or `FIL`. |
| `sensor` Last raw frame | Diagnostic. The most recent BLE frame, for reverse engineering. |
| `button` Temp up, Temp down, Light, Filter, Jets | Each becomes available once its payload is configured. |

Services: `smartouch_spa.send_raw` (write hex bytes to any characteristic)
and `smartouch_spa.press_button`. The diagnostics download includes the GATT
table and raw traffic.

### Why an integration and not an add-on

A custom integration uses Home Assistant's Bluetooth stack, so it works with
a local adapter or with **ESPHome Bluetooth proxies** placed near the spa.
An add-on would need its own BLE adapter access and an MQTT bridge, with no
benefit. If captures show that WiFi mode is a LAN protocol, a WiFi transport
can be added to this same integration.

## Install

You can install through HACS as a custom repository
(`https://github.com/GabrielGoldsteinAnidea/ha-smartouch-spa`, category
Integration), or copy `custom_components/smartouch_spa` into your config
directory. Then restart Home Assistant and go to **Settings → Devices &
services → Add integration → SmarTouch Spa**.

Close the SmarTouch app before connecting. BLE peripherals usually allow
only one connection at a time.

## Development

```bash
pip install homeassistant pytest pytest-asyncio ruff
```

```bash
pytest
```

```bash
ruff check . && ruff format --check .
```

The `spa_core/` package does not depend on Home Assistant, so its tests
run with plain `pytest`. `tests/test_client_sim.py` runs the BLE client
against a simulated spa, and is skipped if `homeassistant` is not installed.

## Disclaimer

This project is not affiliated with Applied Computer Controls or the app
developer. Use it at your own risk: it controls a heater.
