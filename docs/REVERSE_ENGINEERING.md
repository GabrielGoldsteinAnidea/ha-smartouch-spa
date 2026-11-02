# Reverse-engineering procedure

The goal is to fill in every "Unknown" row in [PROTOCOL.md](PROTOCOL.md).
There are three independent sources of evidence. Use at least two, so each
finding is cross-checked:

* **A. Static analysis** of the decompiled APK: what the code says it sends.
* **B. HCI snoop log**: what actually went over the air (no root needed).
* **C. Frida hooks**: what the app wrote and received, with characteristic
  UUIDs and timestamps (needs root, or a patched APK).

You also have **D. the integration itself**. It records every frame it
sends and receives (without the PIN) and lets you send raw bytes from Home
Assistant. Use it to confirm findings.

Prerequisites on your computer: Android platform-tools (`adb`), Python 3,
and optionally [jadx](https://github.com/skylot/jadx), apktool, Android
build-tools (`zipalign`, `apksigner`), `frida-tools`, `objection`, and Wireshark.
On the phone, enable Developer options and USB debugging.

All scripts write into `./captures/`, which is git-ignored because it can
contain your spa PIN and network details.

## 1. Identify the app

```bash
tools/adb/find_package.sh
```

This confirms the package name and shows the permissions. If the app has
Bluetooth permissions but no `INTERNET` permission, WiFi mode must be LAN-only.
If it also has `INTERNET`, check the URLs found in step 2.

## 2. Static analysis (A)

```bash
tools/adb/pull_apk.sh
tools/adb/decompile.sh captures/apk/base.apk
```

**SmarTouch Digital 1.1.2 is a Cordova app.** Its Java code is only the
Cordova shell, so jadx output is not useful. `decompile.sh` detects this and
extracts the JavaScript to `captures/www/assets/www/js/`, plus
`findings/js_uuids.txt` and `findings/js_ble_calls.txt`. The files that
matter are:

* `connection.js`: the service and characteristic UUIDs.
* `navigation.js`: connect sequence, PIN handshake (`bleconnected`, `write_characteristic_mcode_p`, `splitter`), all reads, writes and subscriptions, and the cloud WebSocket (`start_ws`).
* `panel.js`: key codes (`buttons_codes`), set point encoding (`send-temp-value`), and display decoding (`display`, `init_leds`).
* `constants/load_frames.js`: the SVG keypad layouts. The element positions give the digit order and the meaning of each dot.

docs/PROTOCOL.md already records what these files say. Re-check it if the app
updates: run `find_package.sh` for the version, then diff the new
`assets/www/js/` against the old one.

For other apps the jadx findings still apply: `uuids.txt`, `ble_calls.txt`,
`byte_arrays.txt`, `buttons.txt`, `display.txt`, `sockets.txt` and `urls.txt`.

## 3. Capture BLE traffic (B), one action per capture

1. In Developer options, set **Enable Bluetooth HCI snoop log** to Enabled (Full), then turn Bluetooth off and on.
2. For each action, run:

   ```bash
   tools/adb/capture_btsnoop.sh start light
   ```

   In the app: connect, wait about 10 s doing nothing (this is the baseline), press **Light** once, wait 5 s, press it again, and wait 5 s. Write the times in `captures/light.notes`. Then run:

   ```bash
   tools/adb/capture_btsnoop.sh stop light
   ```

3. Repeat for `set_temp` (change the set point once on the app's temperature page, within 98-102 °F), `jets`, and `idle` (connect only, touch nothing for 60 s). The app has no Filter or Temp Up/Down keys for a spa.
4. Analyze the captures:

   ```bash
   python3 tools/analysis/btsnoop_att.py captures/light.btsnoop --writes
   ```

   This shows the written bytes. Expect `6c 30` (`l0`) on the keyboard characteristic for Light.

   ```bash
   python3 tools/analysis/btsnoop_att.py captures/idle.btsnoop --unique
   ```

   This shows the display frames, and how often each one repeats.

## 4. Decode the display

docs/PROTOCOL.md already gives the frame layout from the app's code: 6 bytes,
byte 0 the rightmost digit, bit0 = a ... bit6 = g, bit7 = dot, bytes 4-5
LEDs. Use the captures to confirm it, especially from the `set_temp` capture,
where the display changes from water temperature to the set point and back:

* Bytes that never change are the header or prefix.
* Bytes that change when the shown number changes are the digits.
* A byte that changes in every frame is a counter or checksum.
* Find the byte that shows a known digit. For example, if the display showed
  "102", the byte for "1" lights exactly 2 segments (b, c), so its value has
  exactly 2 bits set. "0" has 6 bits set and "2" has 5. That gives the bit
  order, which you can test quickly:

```python
from spa_core.seven_segment import SegmentMap, SevenSegmentDecoder

SevenSegmentDecoder(SegmentMap.from_order("abcdefg.")).decode(bytes.fromhex("06 3f 5b"))
```

Run this from `custom_components/smartouch_spa/`.

## 5. Frida (C), optional but fastest

```bash
frida -U -f com.mltech.agi.accslv2a -l tools/frida/smartouch_hooks.js
```

This needs a rooted phone with frida-server. On a phone without root, patch
the APK instead:

```bash
objection patchapk -s captures/apk/base.apk
```

Install the patched APK, then attach with:

```bash
frida -U Gadget -l tools/frida/smartouch_hooks.js
```

This logs `GATT` (the full service table), `SUB` (which characteristics the
app subscribes to), `TX` and `RX` with UUIDs, and `TCP`, `UDP` and `URL`
lines for WiFi mode.

To get a debuggable build, which allows Android Studio debugging and HTTPS
MITM with a user CA, run:

```bash
tools/adb/make_debuggable.sh
```

The re-signed APK requires uninstalling the original, which wipes the app's
saved pairing.

## 6. Confirm from Home Assistant (D)

1. Close the SmarTouch app. The module probably accepts only one BLE connection.
2. Install the integration and enter the spa's PIN. The **Auth state** diagnostic sensor should read `N`. `B` means the PIN was rejected, and Home Assistant then asks for it again.
3. Compare the **Display** sensor with the spa panel. Download diagnostics for the GATT table, the unique payloads per characteristic, and the last 200 frames. The PIN and app code are never recorded.
4. Toggle the **Light** entity. If the spa light changes and the entity's state follows, the key code and the light LED bit are both confirmed.
5. Set the thermostat within 98-102 °F and check the panel.
6. Record each result in PROTOCOL.md: change its status to Confirmed and cite the capture or test. If a value is wrong, fix it in `spa_core/protocol.py` and add a test built from the captured frame (PIN and MAC redacted).

To replay a single observed payload by hand:

```yaml
action: smartouch_spa.send_raw
data:
  uuid: "12ead13c-4d06-48b7-a3f9-cdf725acdd87"
  data: "6c 30"
```

The service refuses the MMODE, MCODE, BTNAME and WIFICREDS characteristics, because writes there change the module's owner, name or WiFi settings.
