#!/usr/bin/env bash
# List installed packages that look like the SmarTouch app, and print its
# version/permissions. The permissions tell us which transports it uses
# (BLUETOOTH_CONNECT / ACCESS_WIFI_STATE / INTERNET / CHANGE_WIFI_STATE...).
source "$(dirname "$0")/common.sh"
echo "== Candidate packages"
adb shell pm list packages | sed 's/^package://' | grep -iE 'mltech|accslv|smartouch|smarttouch|acc' || echo "(none matched; set SMARTOUCH_PKG manually)"
echo
echo "== dumpsys for $SMARTOUCH_PKG"
adb shell dumpsys package "$SMARTOUCH_PKG" | grep -E 'versionName|versionCode|targetSdk|permission|flags=' | tee "$OUT_DIR/package_info.txt"
