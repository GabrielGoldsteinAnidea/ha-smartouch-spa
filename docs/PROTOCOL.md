# SmarTouch protocol: what is known

Everything below is labelled **Confirmed** (with a source), **Reported**
(from a third-party source only), or **Unknown**. Update this file as captures
come in; record the app version and capture file each finding came from.

## Hardware and app

| Fact | Status | Source |
|---|---|---|
| The app is "SmarTouch Digital". It controls ACC (Applied Computer Controls) spa packs through the BWF-200 WiFi + Bluetooth module. | Reported | Seller listing at [hottuboutpost.com](https://www.hottuboutpost.com/acc-wifi-module-bwf-200-bluetooth-applied-computer-controls/); [App Store listing](https://apps.apple.com/ve/app/smartouch-digital/id1523914512) |
| The BWF-200 works only with ACC packs SMTD1000, SMTD1100, SMTD1500, SMTD2000 and SMTD3000. It is 2.4 GHz only. | Reported | [bathandspaparts.com BWF-200](https://www.bathandspaparts.com/products/bwf-200) (as quoted in search results; the page could not be fetched from the build environment) |
| The module installs at the equipment box, in place of the existing keypad connection. | Reported | [manuals.plus BWF-200 manual](https://manuals.plus/acc-spas/bwf-200-wifi-and-bluetooth-spa-controller-manual-2) (as quoted in search results) |
| For initial setup you must be within about 20 ft. The module has a factory default network name, and you choose a spa name and a 4-digit PIN. | Reported | same manual |
| The Android package is `com.mltech.agi.accslv2a`, version 1.0.11, minimum Android 5.1. | Reported (third-party APK site) | [ipingguoyuan.com listing](https://www.ipingguoyuan.com/en/review/com.mltech.agi.accslv2a). Verify with `tools/adb/find_package.sh`. |
| The app mirrors the keypad: it sends button presses and shows the 7-segment display. | Owner's observation | Not yet verified from captures |

## Protocol: unknown, to be filled from captures

| Question | How to answer it | Answer |
|---|---|---|
| BLE advertised name / service UUIDs | nRF Connect scan, or `GATT` lines from `tools/frida/smartouch_hooks.js` | Unknown |
| GATT service/characteristic used for display (notify) | `SUB` / `RX` lines (Frida) or NOTIFY handle in `btsnoop_att.py` output | Unknown |
| Characteristic used for button presses (write) and write type | `TX` lines (Frida) / WRITE_CMD vs WRITE_REQ in btsnoop | Unknown |
| Is the PIN sent over BLE, and how (plain, hashed, challenge)? | First writes after connecting, plus the decompiled connect code | Unknown |
| Frame layout: header, length, checksum, digit byte offsets | Diff frames while the display changes (see REVERSE_ENGINEERING.md §4) | Unknown |
| 7-segment bit order | Find a frame showing a known value such as "8" (all segments) or a known temperature | Unknown (default assumption: bit0=a ... bit6=g, bit7=dp) |
| Indicator LEDs (heater, filter, light, jets) present in frames? | Toggle each one and diff | Unknown |
| Button payload per button | One press per capture | Unknown |
| WiFi mode: LAN (direct to module) or cloud relay? Hostnames and ports | `TCP`/`URL`/`UDP` lines (Frida), PCAPdroid capture, `tools/adb/decompile.sh` → `findings/sockets.txt`, `urls.txt` | Unknown |

## Assumptions currently built into the integration

These are design assumptions, not facts. Each one can be changed in the
integration options or by editing `spa_core/profile.py`.

1. **BLE is the transport.** The integration speaks BLE through Home
   Assistant's Bluetooth stack, so ESPHome Bluetooth proxies work. If
   captures show WiFi mode is a simple LAN protocol, a WiFi transport can be
   added next to `client.py`.
2. **Display data comes as notifications.** Digits are a contiguous run of
   one byte per digit at a fixed offset, optionally after a fixed prefix.
3. **A temp button press shows the set point for a few seconds** (default 5 s,
   configurable). Readings inside that window count as the set point, and
   readings outside it count as water temperature.
4. **A press is a single write** of a fixed payload. If captures show a
   press/release pair, a rolling counter, or a checksum, `SpaClient.press`
   needs a codec function instead of a static payload.
5. **No authentication.** If the PIN is needed on each connection, a
   handshake step goes in `SpaClient.ensure_connected`.
