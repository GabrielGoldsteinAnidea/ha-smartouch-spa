# SmarTouch Spa for Home Assistant

A Home Assistant custom integration for spas that use the ACC (Applied
Computer Controls) **SmarTouch Digital** control with the **BWF-200**
WiFi/Bluetooth module, which is the hardware behind the "SmarTouch Digital"
phone app. The repo also includes the tooling to reverse-engineer the app's
protocol.

> **Status: working on one spa, partly verified.** Sign-in with the PIN,
> discovery, the display (water temperature and the ECON message) and the
> light are confirmed on a real spa. The other controls follow the app's
> source (version 1.1.2, a Cordova app with readable JavaScript) and the
> SmarTouch manuals, and have not been seen working yet. See
> [docs/PROTOCOL.md](docs/PROTOCOL.md) for each fact and its status, and
> [docs/MANUAL_COVERAGE.md](docs/MANUAL_COVERAGE.md) for every manual feature
> and whether Home Assistant can reach it.

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
* **Keys.** LITE, JETS, AIR, AUX and SET are single writes of a 2-letter
  code (the app calls them light, jets, aux, aux2 and system). There is no
  Filter key and no way to press two keys at once, so the panel's
  programming menus (filtration periods, options) are out of reach.
* **Key state from the lights.** Each device key sits under a Lo/Hi light
  pair. The selects press a key until its lights match the option you pick,
  and stop if the option is not in your spa's cycle.
* **Clock.** The time of day is written in the app's format, from the
  Clock entity, the Sync clock button, or automatically (an option).
* **Messages.** ECON, the error codes and programming mode are read from
  the display (`spa_core/status.py`).
* **No setup commands.** The integration never sends the module commands
  that change its owner, name, WiFi or PIN. The raw-write service refuses
  those characteristics.

### Entities

| Entity | Notes |
|---|---|
| `climate` Thermostat | Water temperature, set point (direct write), and heating action from the heating LED. |
| `light` Light | State from the light LED; turning it on or off presses the light key only when needed. |
| `select` Jets, Jets 2, Air | Off / Lo / Hi / Lo + Hi from each key's lights; choosing one presses the key until the lights match. |
| `time` Clock | Read from the display when shown; setting it writes the time. |
| `sensor` Status | Normal, Economy, Programming, or an error code (CoLd, OH, HLoH, SEoP, SESH, PSoC/L/H, ToE) with a description. |
| `sensor` Water temperature, Display | The display text, e.g. `102°F`, `ECon`, `12:30`. |
| `binary_sensor` Economy mode, Problem | From the display messages and the overheat light. |
| `binary_sensor` Heating, Filtering, Overheat, Jets/Jets 2/Air low and high, Edit, AM | From the indicator lights. |
| `button` Jets key, Air key, Aux key, Set key (done using spa), Sync clock | One press each. |
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
