#!/usr/bin/env bash
# Stream the app's own log output (start the app first). Many apps log
# BLE payloads or JSON at debug level.
source "$(dirname "$0")/common.sh"
pid=$(adb shell pidof -s "$SMARTOUCH_PKG" | tr -d '\r')
[ -n "$pid" ] || { echo "$SMARTOUCH_PKG is not running" >&2; exit 1; }
adb logcat --pid="$pid" -v threadtime | tee "$OUT_DIR/logcat_$(date +%s).txt"
