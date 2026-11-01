# Shared helpers. Source from the other scripts.
set -euo pipefail
# Unconfirmed package name (from a third-party APK listing). find_package.sh
# searches the phone so you don't have to trust this.
SMARTOUCH_PKG="${SMARTOUCH_PKG:-com.mltech.agi.accslv2a}"
OUT_DIR="${OUT_DIR:-$(pwd)/captures}"
mkdir -p "$OUT_DIR"
need() { command -v "$1" >/dev/null || { echo "missing tool: $1 ($2)" >&2; exit 1; }; }
need adb "Android platform-tools"
adb get-state >/dev/null 2>&1 || { echo "No device. Enable USB debugging and run 'adb devices'." >&2; exit 1; }
