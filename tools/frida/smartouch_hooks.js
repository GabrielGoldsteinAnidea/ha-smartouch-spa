/*
 * Frida hooks for the SmarTouch app: logs every GATT write/notify with its
 * characteristic UUID, and every socket/URL the app opens (WiFi mode: tells
 * us whether control is LAN-local or via a cloud server).
 *
 * Rooted phone with frida-server:
 *   frida -U -f com.mltech.agi.accslv2a -l smartouch_hooks.js
 * Non-rooted (embed Frida gadget):
 *   objection patchapk -s captures/apk/base.apk   # then install the patched APK
 *   frida -U Gadget -l smartouch_hooks.js
 *
 * Uses only public Android SDK APIs (BluetoothGatt, BluetoothDevice,
 * BluetoothGattCallback, java.net.*), so it does not depend on the app's
 * (possibly obfuscated) class names.
 */
'use strict';

function hex(arr, off, len) {
  if (arr === null || arr === undefined) return 'null';
  const start = off || 0;
  const end = len === undefined ? arr.length : start + len;
  const out = [];
  for (let i = start; i < end; i++) out.push(('0' + (arr[i] & 0xff).toString(16)).slice(-2));
  return out.join(' ');
}
function ts() { return new Date().toISOString(); }
function log(tag, msg) { console.log(`${ts()} [${tag}] ${msg}`); }

Java.perform(function () {
  const Gatt = Java.use('android.bluetooth.BluetoothGatt');
  const Device = Java.use('android.bluetooth.BluetoothDevice');

  // ---- outgoing writes (both pre-API33 and API33+ overloads)
  Gatt.writeCharacteristic.overloads.forEach(function (o) {
    o.implementation = function () {
      const c = arguments[0];
      const value = arguments.length >= 2 ? arguments[1] : c.getValue();
      const wtype = arguments.length >= 3 ? arguments[2] : c.getWriteType();
      log('TX', `${c.getUuid()} type=${wtype} ${hex(value)}`);
      return o.apply(this, arguments);
    };
  });
  Gatt.writeDescriptor.overloads.forEach(function (o) {
    o.implementation = function () {
      const d = arguments[0];
      const value = arguments.length >= 2 ? arguments[1] : d.getValue();
      log('DESC', `${d.getCharacteristic().getUuid()}/${d.getUuid()} ${hex(value)}`);
      return o.apply(this, arguments);
    };
  });
  Gatt.setCharacteristicNotification.implementation = function (c, enable) {
    log('SUB', `${c.getUuid()} enable=${enable}`);
    return this.setCharacteristicNotification(c, enable);
  };
  Gatt.readCharacteristic.implementation = function (c) {
    log('READ', `${c.getUuid()}`);
    return this.readCharacteristic(c);
  };

  // ---- incoming: hook the app's own callback class, found at connectGatt time
  const hooked = {};
  function hookCallbackClass(cb) {
    const name = cb.getClass().getName();
    if (hooked[name]) return;
    hooked[name] = true;
    log('INFO', `hooking BluetoothGattCallback subclass ${name}`);
    const K = Java.use(name);
    ['onCharacteristicChanged', 'onCharacteristicRead'].forEach(function (m) {
      if (!K[m]) return;
      K[m].overloads.forEach(function (o) {
        o.implementation = function () {
          const c = arguments[1];
          // API33+ passes the value as an argument; older reads it from the characteristic.
          let value = null;
          for (let i = 2; i < arguments.length; i++) {
            if (arguments[i] !== null && arguments[i].length !== undefined) value = arguments[i];
          }
          if (value === null) value = c.getValue();
          log(m === 'onCharacteristicChanged' ? 'RX' : 'RD', `${c.getUuid()} ${hex(value)}`);
          return o.apply(this, arguments);
        };
      });
    });
    if (K.onServicesDiscovered) {
      K.onServicesDiscovered.implementation = function (gatt, status) {
        const services = gatt.getServices();
        for (let i = 0; i < services.size(); i++) {
          const s = Java.cast(services.get(i), Java.use('android.bluetooth.BluetoothGattService'));
          const chars = s.getCharacteristics();
          for (let j = 0; j < chars.size(); j++) {
            const c = Java.cast(chars.get(j), Java.use('android.bluetooth.BluetoothGattCharacteristic'));
            log('GATT', `service=${s.getUuid()} char=${c.getUuid()} props=0x${c.getProperties().toString(16)}`);
          }
        }
        return this.onServicesDiscovered(gatt, status);
      };
    }
  }
  Device.connectGatt.overloads.forEach(function (o) {
    o.implementation = function () {
      log('CONN', `connectGatt ${this.getAddress()} name=${this.getName()}`);
      for (let i = 0; i < arguments.length; i++) {
        const a = arguments[i];
        if (a !== null && typeof a === 'object' && a.getClass) {
          try {
            if (Java.use('android.bluetooth.BluetoothGattCallback').class.isAssignableFrom(a.getClass())) {
              hookCallbackClass(a);
            }
          } catch (e) { /* not a Java object we care about */ }
        }
      }
      return o.apply(this, arguments);
    };
  });

  // ---- network (WiFi mode)
  const Socket = Java.use('java.net.Socket');
  Socket.connect.overloads.forEach(function (o) {
    o.implementation = function () {
      log('TCP', `connect ${arguments[0]}`);
      return o.apply(this, arguments);
    };
  });
  const Dgram = Java.use('java.net.DatagramSocket');
  Dgram.send.implementation = function (p) {
    log('UDP', `send ${p.getSocketAddress()} ${hex(p.getData(), p.getOffset(), p.getLength())}`);
    return this.send(p);
  };
  Dgram.receive.implementation = function (p) {
    const r = this.receive(p);
    log('UDP', `recv ${p.getSocketAddress()} ${hex(p.getData(), p.getOffset(), p.getLength())}`);
    return r;
  };
  const URL = Java.use('java.net.URL');
  URL.$init.overload('java.lang.String').implementation = function (s) {
    log('URL', s);
    return this.$init(s);
  };
  log('INFO', 'hooks installed');
});
