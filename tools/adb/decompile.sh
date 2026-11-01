#!/usr/bin/env bash
# Decompile base.apk with jadx and grep for the facts we need:
# GATT UUIDs, BLE calls, sockets/URLs (WiFi mode: LAN or cloud?), and
# byte arrays that look like command tables.
set -euo pipefail
APK="${1:-captures/apk/base.apk}"
OUT="${2:-captures/jadx}"
command -v jadx >/dev/null || { echo "install jadx: https://github.com/skylot/jadx/releases" >&2; exit 1; }
jadx --deobf -d "$OUT" "$APK" || true   # jadx exits non-zero on partial failures
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
echo "Also check for a Flutter/React Native/Xamarin app (logic would be in libapp.so / index.android.bundle / assemblies):"
unzip -l "$APK" | grep -E 'libflutter|libapp.so|index.android.bundle|assemblies/' || echo "  none found: plain Java/Kotlin"
