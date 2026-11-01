# Reverse-engineering procedure

The goal is to fill in every "Unknown" row in [PROTOCOL.md](PROTOCOL.md).
There are three independent sources of evidence. Use at least two, so each
finding is cross-checked:

* **A. Static analysis** of the decompiled APK: what the code says it sends.
* **B. HCI snoop log**: what actually went over the air (no root needed).
* **C. Frida hooks**: what the app wrote and received, with characteristic
  UUIDs and timestamps (needs root, or a patched APK).

You also have **D. the integration's discovery mode**. It subscribes to
everything the module notifies and lets you send raw bytes from Home
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

Then read the files in `captures/findings/`:

* `uuids.txt`: GATT service and characteristic UUIDs. These are the most valuable single result.
* `ble_calls.txt`: where it writes and subscribes. Open those classes in jadx-gui and follow how the byte arrays are built (the header, the checksum, and the PIN handling).
* `byte_arrays.txt` and `buttons.txt`: the button command table, if it is static.
* `display.txt`: the code that turns received bytes into the on-screen display. That code tells you the frame layout and the segment bit order directly.
* `sockets.txt` and `urls.txt`: the WiFi-mode transport.
* The script also reports whether the app is Flutter, React Native or Xamarin. If it is, the logic lives in `libapp.so`, `index.android.bundle` or .NET assemblies, and jadx will not show it. Tell me which framework it is and I will adjust the tooling.

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

3. Repeat for `temp_up`, `temp_down`, `filter`, `jets`, and `idle` (connect only, touch nothing for 60 s).
4. Analyze the captures:

   ```bash
   python3 tools/analysis/btsnoop_att.py captures/light.btsnoop --writes
   ```

   This shows the button bytes.

   ```bash
   python3 tools/analysis/btsnoop_att.py captures/idle.btsnoop --unique
   ```

   This shows the display frames, and how often each one repeats.

## 4. Decode the display

Use the `temp_up` capture, where the display changes from water temperature
to the set point and back:

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

1. Install the integration. With no options set, it runs in **discovery mode**.
2. Close the SmarTouch app. A BLE peripheral usually accepts only one central at a time.
3. Watch the **Last raw frame** sensor, or download diagnostics. Diagnostics include the GATT table, the unique payloads per characteristic, and the last 200 frames.
4. Replay a button you found:

   ```yaml
   action: smartouch_spa.send_raw
   data:
     uuid: "<write characteristic uuid>"
     data: "<hex payload>"
   ```

   If the light toggles, the finding is confirmed.
5. Enter the confirmed values in **Settings → Devices & services → SmarTouch Spa → Configure**. The climate and button entities then become available.
6. Commit the confirmed values as defaults in `spa_core/profile.py`, and update PROTOCOL.md with the source capture for each one.
