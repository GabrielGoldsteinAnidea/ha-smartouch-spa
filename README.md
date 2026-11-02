# SmarTouch Spa for Home Assistant

A Home Assistant custom integration for spas that use the ACC (Applied
Computer Controls) **SmarTouch Digital** control with the **BWF-200**
WiFi/Bluetooth module, which is the hardware behind the "SmarTouch Digital"
phone app. The repo also includes the tooling to reverse-engineer the app's
protocol.

> **Status: protocol mapped from the app's source, not yet tested on a spa.**
> The app (version 1.1.2) is a Cordova app, so its protocol logic is readable
> JavaScript. Every value the integration uses was taken from that code. What
> the module does in reply has not been observed yet. See
> [docs/PROTOCOL.md](docs/PROTOCOL.md) for each fact, its source and its
> status, and [docs/REVERSE_ENGINEERING.md](docs/REVERSE_ENGINEERING.md) for
> the capture procedure that will confirm them.

## How it works

The module exposes one BLE service with a characteristic per function. The
integration does what the app does:

* **Sign in.** On every connection it writes its own random app code plus
  your 4-digit PIN, the same way a second phone joins. The module answers
  with its auth state (`N` normal user, `M` owner, `B` wrong PIN). A wrong
  PIN starts Home Assistant's re-authentication flow.
* **Display → state.** The module notifies the keypad display as 6 bytes:
  four 7-segment digits and two bytes of indicator LEDs
  (`spa_core/protocol.py`). Temperatures shown within a few seconds of a set
  point change count as the **set point**; all others count as **water
  temperature** (`spa_core/display.py`).
* **Set temperature directly.** The app writes the set point as text, such as
  `102F`, to its own characteristic. The integration sends exactly the values
  the app offers: 40-104 °F, or the app's matching °C values.
* **Keys.** Light, Jets, Aux, Aux2 and System are single writes of a 2-letter
  code. There is no Filter key in the app; filtering is an indicator only.
* **No setup commands.** The integration never sends the module commands
  that change its owner, name, WiFi or PIN. The raw-write service refuses
  those characteristics.

### Entities

| Entity | Notes |
|---|---|
| `climate` Thermostat | Water temperature, set point (direct write), and heating action from the heating LED. |
| `light` Light | State from the light LED; turning it on or off presses the light key only when needed. |
| `sensor` Water temperature, Display | The display text, e.g. `102°F`, `38.5°C`, `12:30`. |
| `binary_sensor` Heating, Filtering, Overheat, Jets low/high | From the indicator LEDs. Jets 2, Air, Edit and AM exist too, disabled by default. |
| `button` Jets | Aux, Aux 2 and System exist too, disabled by default until their function on your spa is known. |
| `sensor` Last raw frame, Auth state | Diagnostic. |

Services: `smartouch_spa.send_raw` (write hex bytes to a non-configuration
characteristic) and `smartouch_spa.press_button`. The diagnostics download
includes the GATT table and raw traffic, with the PIN and app code redacted.

### Why an integration and not an add-on

A custom integration uses Home Assistant's Bluetooth stack, so it works with
a local adapter or with **ESPHome Bluetooth proxies** placed near the spa.
An add-on would need its own BLE adapter access and an MQTT bridge, with no
benefit. The app's WiFi mode goes through the vendor's cloud
(`accsmartlink.com`), not the local network, so there is no local WiFi
protocol to use instead.

## Install

You can install through HACS as a custom repository
(`https://github.com/GabrielGoldsteinAnidea/ha-smartouch-spa`, category
Integration), or copy `custom_components/smartouch_spa` into your config
directory. Then restart Home Assistant. The spa should be discovered
automatically; otherwise go to **Settings → Devices & services → Add
integration → SmarTouch Spa**. You need the spa's 4-digit PIN.

Close the SmarTouch app before connecting. BLE peripherals usually allow
only one connection at a time.

## Development

```bash
pip install homeassistant bleak bleak-retry-connector pytest pytest-asyncio ruff
```

```bash
pytest
```

```bash
ruff check . && ruff format --check .
```

The `spa_core/` package does not depend on Home Assistant, so its tests
run with plain `pytest`. `tests/test_client_sim.py` runs the BLE client
against a simulated module, and is skipped if `bleak` is not installed.

## Disclaimer

This project is not affiliated with Applied Computer Controls or the app
developer. Use it at your own risk: it controls a heater.
