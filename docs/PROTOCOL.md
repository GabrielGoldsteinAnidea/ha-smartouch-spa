# SmarTouch protocol: what is known

Every fact below carries one of these labels:

* **Confirmed**: two independent sources agree, or a replay test succeeded.
* **Static**: read directly from the app's own source code (one source). Treat it as what the app *sends* and *expects*; what the module does in response is still to be observed.
* **Inferred**: a conclusion drawn from static evidence that the code does not state outright. The reasoning is given.
* **Reported**: from a third-party source only.
* **Unknown**.

Record the app version and capture file each finding came from.

## Hardware and app

| Fact | Status | Source |
|---|---|---|
| The app is "SmarTouch Digital". It controls ACC (Applied Computer Controls) spa packs through the BWF-200 WiFi + Bluetooth module. | Reported | Seller listing at [hottuboutpost.com](https://www.hottuboutpost.com/acc-wifi-module-bwf-200-bluetooth-applied-computer-controls/); [App Store listing](https://apps.apple.com/ve/app/smartouch-digital/id1523914512) |
| The BWF-200 works only with ACC packs SMTD1000, SMTD1100, SMTD1500, SMTD2000 and SMTD3000. It is 2.4 GHz only. | Reported | [bathandspaparts.com BWF-200](https://www.bathandspaparts.com/products/bwf-200) (as quoted in search results; the page could not be fetched from the build environment) |
| The module installs at the equipment box, in place of the existing keypad connection. | Reported | [manuals.plus BWF-200 manual](https://manuals.plus/acc-spas/bwf-200-wifi-and-bluetooth-spa-controller-manual-2) (as quoted in search results) |
| For initial setup you must be within about 20 ft. The module has a factory default network name, and you choose a spa name and a 4-digit PIN. | Reported | same manual |
| The Android package is `com.mltech.agi.accslv2a`. The installed version on the owner's phone is **1.1.2** (versionCode 10102, minSdk 22, targetSdk 31). | Confirmed | `tools/adb/find_package.sh` on the owner's phone, 2026-11-02; agrees with the [ipingguoyuan.com listing](https://www.ipingguoyuan.com/en/review/com.mltech.agi.accslv2a) for the package name (that listing reports the older version 1.0.11) |
| Permissions: `BLUETOOTH_SCAN`, `BLUETOOTH_CONNECT`, `INTERNET`, `ACCESS_LOCAL_NETWORK`, plus media/storage and notifications. | Confirmed | `dumpsys package` via `find_package.sh`, app 1.1.2 |
| The app is an **Apache Cordova** (hybrid HTML/JavaScript) app. Its own Java code is only the Cordova shell (`com.mltech.agi.accslv2a.MainActivity`, `R`, `BuildConfig`). All protocol logic is plain JavaScript in `assets/www/js/`. BLE goes through `cordova-plugin-ble-central` 1.6.3. | Static | `base.apk` 1.1.2: `assets/www/cordova_plugins.js` (plugin list and versions); class names in `classes.dex` |
| The app mirrors the keypad: it sends button presses and shows the 7-segment display with indicator LEDs. | Static | `assets/www/js/panel.js` `link_buttons()` and `display()`; owner's observation agrees |

All "Static" citations below are paths inside `base.apk` version 1.1.2.
Run `tools/adb/pull_apk.sh` and `unzip captures/apk/base.apk 'assets/www/js/*' -d captures/www` to
reproduce them. jadx is not needed for this app.

## GATT layout

| Fact | Status | Source |
|---|---|---|
| Service `c5a092a5-2202-4ac6-8734-2e8ff796094d` ("operation"). | Static | `js/connection.js:2` |
| The module advertises that service UUID, because the app finds spas with a scan filtered on it. | Inferred | `js/navigation.js:923` `ble.startScan([SERVICE_UUID_OPERATION], ...)`. An Android scan filter on a service UUID only matches devices whose advertisement carries it. A PC scan on 2026-11-02 saw 28 devices and none of them advertised it, but the spa was probably out of range, so this is not yet cross-checked. |
| Characteristics, all in that service: | Static | `js/connection.js:5-16` |

| Name in app | UUID | Direction | Format |
|---|---|---|---|
| `KEYBOARD` | `12ead13c-4d06-48b7-a3f9-cdf725acdd87` | write | ASCII key code, 2 chars |
| `TEMPERATURE` | `0daecf8f-2352-4ae8-bdb8-4ae862f041e3` | write | ASCII set point, 4 chars |
| `TIME` | `8cea517c-2d76-4190-ae05-2e222a3caacb` | write | ASCII `HHMM` + `A`/`P` |
| `SESSION` | `c67c0b5f-0f50-44fc-a0f9-449ff1f476f1` | write | sauna only, ASCII 3 digits |
| `DISPLAY` | `30105eb3-19dc-4621-a227-a917b43162a6` | notify + read | 6 raw bytes |
| `WIFICREDS` | `5eb76cac-ada4-43c2-9ed0-b80547542e9f` | write | `ssid+password`, chunked |
| `VERSION` | `207da212-c2fd-43b5-9664-ac15166364d2` | read | ASCII JSON, includes `ptype` (0/1 spa, 2 sauna, 3 chiller) and `oem` |
| `WIFIMAC` | `aefc6b90-26f1-4842-b720-3d47f4a087cf` | read | ASCII, 12 hex chars |
| `MMODE` | `984cdbfb-446b-43b2-a879-c857a9a0f638` | notify + write | 1 ASCII char: auth state and module commands |
| `MCODE` | `6436e996-e573-4ff7-83fd-d0ea0bd09458` | write | auth code + PIN, chunked |
| `BTNAME` | `f8733ee9-6e45-485a-a8a1-9e4e8bdb0536` | write | ASCII spa name, at most 8 chars |
| `CRAS` | `71d67ace-65d6-4d28-b08f-f54735e7d50c` | notify | WiFi scan results `status+ssid|channel|rssi|auth` |

Directions come from which plugin call the app uses on each characteristic
(`ble.write`, `ble.read`, `ble.startNotification`) in `js/navigation.js`. The
real GATT property flags are not yet observed.

| Fact | Status | Source |
|---|---|---|
| Every write the app makes uses `ble.write`, which is **write with response**. The app never calls `writeWithoutResponse`. | Static | `js/navigation.js` (every `ble.write(...)` call); the plugin maps `write` to `BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT` in [`BLECentralPlugin.java` lines 310-316 at tag 1.6.3](https://github.com/don/cordova-plugin-ble-central/blob/1.6.3/src/android/BLECentralPlugin.java#L310-L316) |
| On Android the app requests MTU 180 after connecting. Every payload it sends is 20 bytes or less anyway. | Static | `js/navigation.js:687-691` `blerequestMtu_p()`, called at `:720` |

## Connection and authentication

| Fact | Status | Source |
|---|---|---|
| Connect sequence: request MTU 180, subscribe `MMODE`, subscribe `DISPLAY`, subscribe `CRAS` (100 ms between each), read `WIFIMAC`, read `VERSION`, then write the auth string to `MCODE`. | Static | `js/navigation.js:695-735` `bleconnected()` |
| **The PIN is sent on every connection.** The auth string is `mcode + pass`. | Static | `js/navigation.js:501-503` `write_characteristic_mcode_p()`; called on every connect at `:735` |
| `mcode` is a random 16-character base64url string (12 random bytes), generated once per app install and stored in `mmcode.json`. | Static | `js/accp.js:105-112` and `RandomBase64url()` at `:127-139` |
| `pass` is the 4-digit PIN when typed on the PIN page. The phone that set the spa up (the "master") uses the PIN plus 8 random base64url characters (12 total). | Static | PIN page: `js/navigation.js:169-185` (`pass = ('000' + pass).slice(-4)`). Master setup: `:190-231` (`rndm` at `:208`, `pass = pass + rndm` just after). |
| Strings longer than 19 chars are split into chunks: `"0" + first 19`, `"2" + next 19` for middle chunks, `"9" + rest`. A string of 19 chars or less is sent as one write with no flag. So a 16-char mcode + 4-digit PIN is sent as two writes: `"0" + 19 chars`, then `"9" + 1 char`. | Static | `js/navigation.js:1255-1268` `splitter()` and `:1283` `sendBleString_p()`. (`js/splitter.js` has a different splitter, but `index.html` never loads it.) |
| `MMODE` notifications report the auth state: `F` = unprogrammed (setup page), `B` = PIN needed or wrong (PIN page), `M` = authorised as master, `N` = authorised as a normal user. The control page opens only on `M` or `N`. | Static | `js/navigation.js:361-366` |
| A new device (such as Home Assistant) can authorise by sending its own mcode + the 4-digit PIN and should then receive `N`. | Inferred | That is exactly what a second phone does: it has no stored pass, gets `B`, and the PIN page sends `mcode + PIN` (`:169-185`). What the module then replies has not been observed. |
| Writes to `MMODE` are module commands: `D` force disconnect, `R` restart in 5 s, `C` clear master code, `S` store new master, `Z`/`W` WiFi scan. **Home Assistant must never send `C`, `S` or `R`.** | Static | `js/navigation.js:226`, `:235`, `:240`, `:711`; `js/panel.js` WiFi page timer |
| Both master and normal users get the temperature page. Only the master gets the share page and the setup buttons. | Static | `index.html` `master-spa-nav` / `normal-spa-nav`; `js/navigation.js` `prepare_main_page()` |

## Buttons

| Fact | Status | Source |
|---|---|---|
| A press is one write of a 2-char ASCII code to `KEYBOARD`. There is no press/release pair, counter or checksum. | Static | `js/panel.js:33-40` (click handler sends `buttons_codes[...]` once); `js/navigation.js:519-531` writes `str2arr(keys)` |
| Codes: `l0` light, `j0` jets, `a0` aux, `x0` aux2, `s0` system, `u0` up, `d0` down, `u1` set-temp, `d1` set-time. | Static | `js/panel.js:4-7` `buttons_codes` |
| The spa panel this app version draws has only **Aux, Aux2, Jets, Light and System**. Up, Down, Set-temp and Set-time appear only in an unused `spa_bluetooth` layout. | Static | `window.frames.spa` in `js/constants/load_frames.js`. `prepare_main_page()` loads `spa`, not `spa_bluetooth`. |
| **There is no Filter button.** Filtering appears only as an indicator LED. | Static | same; no `button-filter*` element exists in any layout |
| What System, Aux and Aux2 do on this spa. | Unknown | Needs a live test on the panel |

## Set temperature

| Fact | Status | Source |
|---|---|---|
| The app sets the temperature **directly**, by writing a 4-char ASCII value to `TEMPERATURE`. In °F that is the integer plus `F`, zero-padded (`102F`, `099F`). In °C it is tenths of a degree plus `C` (`385C` = 38.5 °C). | Static | `js/panel.js:180-196` |
| The app offers 40-104 °F for a spa. Its °C list is the °F list converted with its own rounding (`f2c`), so it only ever sends °C values that match a whole °F. | Static | `js/panel.js:45-53` `device_limits.spa`; `:310-315` `f2c()`; `:107-129` `fill_opts_temp_select()` |
| Whether the module applies the value directly or simulates button presses, and whether the display then shows the new set point. | Unknown | Needs a live test |

## Display frame

| Fact | Status | Source |
|---|---|---|
| A display frame is a `DISPLAY` notification of 6 bytes. There is no header, length or checksum. The app converts it to 12 hex chars and ignores anything else. | Static | `js/navigation.js:325-334`; `js/panel.js:370-372` (`rx.length == 12`) |
| Bytes 0-3 are the four digits. **Byte 0 is the rightmost digit**, byte 3 the leftmost. | Static (geometry) | Digit `d0` segment `a` sits at x≈156 and `d3` at x≈16 in `window.frames.spa`, so display text is bytes 3, 2, 1, 0 |
| Segment bit order is bit0 = a ... bit6 = g, bit7 = a dot (`h`). | Static | `js/panel.js:334` `snames = [a..h]` and `:375` (`mm <<= 1`) |
| The dot means something different at each position. Digits 3 and 2: a decimal point at the bottom right. Digit 1: a dot at the top left (with digit 2's dot it forms a colon, as in a clock). Digit 0: a degree sign at the top left of the unit letter. | Inferred | Ellipse positions of `digit-dN-sh` in `window.frames.spa`: d3/d2 at the `d` (bottom) row, d1/d0 at the `a` (top) row |
| A first byte of `b9` (C plus dot) means the spa shows °C; `f1` (F plus dot) means °F. | Static | `js/panel.js:382-389` |
| Byte 4 LEDs, bit0 upward: heating, air high, jets low, jets high, filtering, edit, overheat, AM. | Static | `js/panel.js:353-361` `segments[4]` |
| Byte 5 LEDs: bits 0-3 unused; bit4 light, bit5 jets2 high, bit6 jets2 low, bit7 air low. | Static | `js/panel.js:363-367` and `:376` |
| Which displayed temperature is the set point and which is the water temperature. The `edit` LED is a candidate for "showing the set point". | Unknown | Needs a live capture while changing the set point |

## WiFi mode

| Fact | Status | Source |
|---|---|---|
| **WiFi mode is a cloud relay, not a LAN protocol.** The app opens a WebSocket to `wss://accsmartlink.com/wsa/{wifimac}/{M|N}/5905551600/{token}`. | Static | `js/navigation.js:96`, `:879`, `:959-1016` `start_ws()` |
| `token` = hex SHA-256 of `wifimac + mode + "5905551600" + mcode + pass`. The constant `5905551600` is likely an expiry timestamp (the year 2157), but the code does not say so. | Static / Inferred | `js/navigation.js:879`; `js/accp.js` `digestMessage()` |
| Messages sent are JSON: `{"keysec": "l0"}`, `{"temp": "102F"}`, `{"time": ...}`, `{"session": ...}`. The server sends `{"dsp": "<12 hex>"}`, `stsR`, and on connect `mmode`, `ptype`, `oem`. | Static | `js/navigation.js:600-607` `write_characteristic_wifi()`; `:987-1010` (`onmessage`) |
| No LAN socket, local IP or mDNS code exists. The `ACCESS_LOCAL_NETWORK` permission is requested but unused by the JavaScript. | Static | No `ws://`, IP literal or socket plugin in `assets/www`; the plugin list in `cordova_plugins.js` has no TCP/UDP plugin |

## Still unknown (needs the spa)

1. Whether the module accepts Home Assistant's own mcode + PIN and replies `N`.
2. What System, Aux and Aux2 do.
3. How the display distinguishes set point from water temperature, and whether a `TEMPERATURE` write makes the display show the set point.
4. Whether each LED bit means what its name in the app says, on this spa.
5. Whether the module allows a second BLE connection while the phone is connected (assumed not).

## Assumptions currently built into the integration

1. **BLE is the transport.** WiFi mode is a cloud relay (see above), so a WiFi transport would depend on the vendor's server. It is not built.
2. **Home Assistant authenticates as a normal (`N`) user** with its own random mcode and the 4-digit PIN. This is inferred (see "Connection and authentication").
3. **A temp change shows the set point for a few seconds** (default 5 s, configurable). Readings in that window after a `TEMPERATURE` write count as the set point, and other readings count as water temperature. Until the display shows a set point, the climate entity reports the last value it sent.
4. **LED names are taken from the app.** The `light` entity uses the byte-5 bit-4 LED for its state and toggles with `l0`.
5. **Only payloads the app's spa layout sends are exposed**: `l0`, `j0`, `a0`, `x0`, `s0`, and `TEMPERATURE` writes within 40-104 °F.
