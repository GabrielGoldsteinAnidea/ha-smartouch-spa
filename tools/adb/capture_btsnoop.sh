#!/usr/bin/env bash
# Capture the app's BLE traffic with Android's HCI snoop log (no root needed).
# Reference: https://source.android.com/docs/core/connect/bluetooth/verifying_debugging
#
# Procedure (do ONE action per capture so the bytes are easy to attribute):
#   1. Developer options -> "Enable Bluetooth HCI snoop log" -> Enabled/Full.
#   2. Toggle Bluetooth off and on (the setting applies on BT restart).
#   3. Run:  capture_btsnoop.sh start "light_on_off"
#      In the app, connect over Bluetooth, wait 10s idle (baseline), then do
#      the action; say it out loud / note wall-clock times in the label file.
#   4. Run:  capture_btsnoop.sh stop "light_on_off"
source "$(dirname "$0")/common.sh"
cmd="${1:-}"; label="${2:-capture}"
case "$cmd" in
  start)
    # Best effort; most non-rooted phones require the Developer options toggle instead.
    adb shell setprop persist.bluetooth.btsnooplogmode full 2>/dev/null || true
    echo "mode: $(adb shell getprop persist.bluetooth.btsnooplogmode | tr -d '\r')"
    date -u +%FT%TZ > "$OUT_DIR/$label.start"
    echo "Started '$label' at $(cat "$OUT_DIR/$label.start"). Perform the action in the app now."
    echo "Write what you pressed and when into $OUT_DIR/$label.notes"
    ;;
  stop)
    date -u +%FT%TZ > "$OUT_DIR/$label.stop"
    work="$OUT_DIR/$label.bugreport"; mkdir -p "$work"
    # Direct pull works on some phones/rooted devices; bugreport always includes the log.
    if adb pull /data/misc/bluetooth/logs/btsnoop_hci.log "$OUT_DIR/$label.btsnoop" 2>/dev/null; then
      echo "pulled directly"
    else
      echo "taking bugreport (1-3 minutes)..."
      adb bugreport "$work/bugreport.zip"
      unzip -o -q "$work/bugreport.zip" -d "$work"
      f=$(find "$work" -name 'btsnoop_hci.log*' | sort | tail -1)
      [ -n "$f" ] || { echo "btsnoop_hci.log not in bugreport; is the snoop log enabled?" >&2; exit 1; }
      cp "$f" "$OUT_DIR/$label.btsnoop"
    fi
    python3 "$(dirname "$0")/../analysis/btsnoop_att.py" "$OUT_DIR/$label.btsnoop" > "$OUT_DIR/$label.att.txt" || true
    echo "ATT dump: $OUT_DIR/$label.att.txt ($(wc -l < "$OUT_DIR/$label.att.txt") lines)"
    ;;
  *) echo "usage: $0 start|stop <label>" >&2; exit 2;;
esac
