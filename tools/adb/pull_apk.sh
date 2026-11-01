#!/usr/bin/env bash
# Pull the installed APK(s). Play Store installs are often split APKs
# (base.apk + split_config.*.apk); all parts are pulled.
source "$(dirname "$0")/common.sh"
dest="$OUT_DIR/apk"; mkdir -p "$dest"
adb shell pm path "$SMARTOUCH_PKG" | sed 's/^package://' | tr -d '\r' | while read -r path; do
  echo "pulling $path"
  adb pull "$path" "$dest/$(basename "$path")"
done
ls -la "$dest"
