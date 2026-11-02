#!/usr/bin/env bash
# Decompile base.apk with jadx and grep for the facts we need:
# GATT UUIDs, BLE calls, sockets/URLs (WiFi mode: LAN or cloud?), and
# byte arrays that look like command tables.
set -euo pipefail
APK="${1:-captures/apk/base.apk}"
OUT="${2:-captures/jadx}"
if command -v jadx >/dev/null; then
  jadx --deobf -d "$OUT" "$APK" || true   # jadx exits non-zero on partial failures
else
  echo "jadx not found (https://github.com/skylot/jadx/releases): skipping the Java decompile. Cordova apps do not need it." >&2
fi
SRC="$OUT/sources"
R="$OUT/../findings"; mkdir -p "$R"
g() { grep -rnE --include='*.java' "$@" "$SRC" || true; }
g -i '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' > "$R/uuids.txt"
g 'writeCharacteristic|setCharacteristicNotification|onCharacteristicChanged|BluetoothGatt\b|connectGatt' > "$R/ble_calls.txt"
g 'new Socket\(|DatagramSocket|InetSocketAddress|SocketChannel|WebSocket|MqttClient|mqtt' > "$R/sockets.txt"
g -i 'https?://' > "$R/urls.txt"
g 'new byte\[\] *\{' > "$R/byte_arrays.txt"
g -i 'segment|seg7|7seg|digit|display|led' > "$R/display.txt"
g -i 'temp(_)?up|temp(_)?down|light|filter|jet|pump|blower|button|key(code)?' > "$R/buttons.txt"
# Native libs would mean protocol code may live in C/C++ (look at lib/*/ in the APK).
unzip -l "$APK" | grep -E '\.so$' > "$R/native_libs.txt" || true
wc -l "$R"/*.txt
echo "Also check for a Cordova/Flutter/React Native/Xamarin app:"
if unzip -l "$APK" 'assets/www/cordova.js' >/dev/null 2>&1; then
  echo "  Cordova: the logic is plain JavaScript in assets/www/js/. Extracting to $R/../www (jadx output is only the shell)."
  unzip -o -q "$APK" 'assets/www/js/*' 'assets/www/index.html' 'assets/www/cordova_plugins.js' -d "$R/../www" || true
  g() { grep -rnE --include='*.js' "$@" "$R/../www/assets/www/js" || true; }
  g -i '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' > "$R/js_uuids.txt"
  g 'ble\.(write|read|startNotification|connect)|WebSocket' > "$R/js_ble_calls.txt"
  wc -l "$R"/js_*.txt
fi
unzip -l "$APK" | grep -E 'libflutter|libapp.so|index.android.bundle|assemblies/' || echo "  no Flutter/React Native/Xamarin markers"
