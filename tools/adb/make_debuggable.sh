#!/usr/bin/env bash
# Rebuild the APK with android:debuggable="true" and a network security
# config that trusts user-installed CAs (needed to MITM HTTPS in WiFi mode).
# Then you can: attach Android Studio's debugger, use `adb shell run-as`,
# and use Frida via objection without root.
#
# WARNING: installing a re-signed APK requires uninstalling the original
# (different signature), which erases the app's saved spa pairing/PIN.
set -euo pipefail
IN_DIR="${1:-captures/apk}"; WORK="${2:-captures/rebuild}"
for t in apktool zipalign apksigner keytool; do command -v $t >/dev/null || { echo "missing $t" >&2; exit 1; }; done
rm -rf "$WORK"; mkdir -p "$WORK/signed"
apktool d -f "$IN_DIR/base.apk" -o "$WORK/base"
man="$WORK/base/AndroidManifest.xml"
grep -q 'android:debuggable' "$man" || sed -i 's/<application /<application android:debuggable="true" /' "$man"
mkdir -p "$WORK/base/res/xml"
cat > "$WORK/base/res/xml/st_network_security_config.xml" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
  <base-config cleartextTrafficPermitted="true">
    <trust-anchors><certificates src="system"/><certificates src="user"/></trust-anchors>
  </base-config>
</network-security-config>
XML
sed -i 's/android:networkSecurityConfig="[^"]*"//' "$man"
sed -i 's/<application /<application android:networkSecurityConfig="@xml\/st_network_security_config" /' "$man"
apktool b "$WORK/base" -o "$WORK/base-unsigned.apk"
ks="$WORK/debug.keystore"
keytool -genkeypair -keystore "$ks" -storepass android -keypass android -alias st -keyalg RSA -keysize 2048 -validity 3650 -dname "CN=smartouch-re" >/dev/null 2>&1
sign() { zipalign -f -p 4 "$1" "$2.aligned"; apksigner sign --ks "$ks" --ks-pass pass:android --out "$2" "$2.aligned"; rm "$2.aligned"; }
sign "$WORK/base-unsigned.apk" "$WORK/signed/base.apk"
# Split APKs must be signed with the same key.
for s in "$IN_DIR"/split_*.apk; do [ -e "$s" ] && sign "$s" "$WORK/signed/$(basename "$s")"; done
echo "Install with:"
echo "  adb uninstall ${SMARTOUCH_PKG:-com.mltech.agi.accslv2a}"
echo "  adb install-multiple $WORK/signed/*.apk"
