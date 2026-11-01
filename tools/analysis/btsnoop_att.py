#!/usr/bin/env python3
"""Extract BLE GATT (ATT) traffic from an Android btsnoop_hci.log.

Prints one line per ATT write / notification / indication / read response,
so button presses in the SmarTouch app can be correlated with bytes written,
and display changes with notifications.

btsnoop format (as written by Android's Bluetooth stack):
  file header: b"btsnoop\\0", uint32 BE version (1), uint32 BE datalink
               (1002 = HCI UART/H4, first byte of each packet is the H4 type)
  record:      uint32 orig_len, uint32 incl_len, uint32 flags,
               uint32 drops, int64 timestamp (microseconds since 0000-01-01)
               -- all big-endian -- followed by incl_len bytes of packet.
  flags bit0:  0 = sent (host -> controller), 1 = received
HCI ACL (H4 type 0x02): uint16 LE handle|PB|BC, uint16 LE length, payload.
L2CAP basic header: uint16 LE length, uint16 LE CID; CID 0x0004 = ATT.

Usage:
  btsnoop_att.py btsnoop_hci.log                # all ATT lines
  btsnoop_att.py btsnoop_hci.log --unique       # distinct payloads per handle
  btsnoop_att.py btsnoop_hci.log --handle 0x0012
Wireshark opens btsnoop files natively too; this script exists to get a
plain-text, diffable view for press-by-press correlation.
"""

from __future__ import annotations

import argparse
import struct
import sys
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta

BTSNOOP_MAGIC = b"btsnoop\x00"
DATALINK_H4 = 1002
DATALINK_HCI_UNENCAP = 1001
H4_ACL = 0x02
ATT_CID = 0x0004
# Microseconds between 0000-01-01 and 1970-01-01 as used by btsnoop.
BTSNOOP_EPOCH_DELTA_US = 0x00DCDDB30F2F8000

ATT_OPCODES = {
    0x0A: "READ_REQ",
    0x0B: "READ_RSP",
    0x12: "WRITE_REQ",
    0x13: "WRITE_RSP",
    0x1B: "NOTIFY",
    0x1D: "INDICATE",
    0x52: "WRITE_CMD",
}
HANDLE_OPCODES = {0x0A, 0x12, 0x1B, 0x1D, 0x52}


@dataclass
class AttPacket:
    time: datetime
    received: bool
    conn: int
    opcode: int
    handle: int | None
    value: bytes

    @property
    def name(self) -> str:
        return ATT_OPCODES.get(self.opcode, f"OP_{self.opcode:02x}")


def _records(data: bytes) -> Iterator[tuple[int, int, bytes]]:
    if data[:8] != BTSNOOP_MAGIC:
        raise ValueError("not a btsnoop file (bad magic)")
    _version, datalink = struct.unpack(">II", data[8:16])
    if datalink not in (DATALINK_H4, DATALINK_HCI_UNENCAP):
        raise ValueError(f"unsupported datalink {datalink}")
    off = 16
    while off + 24 <= len(data):
        _orig, incl, flags, _drops, ts = struct.unpack(">IIIIq", data[off : off + 24])
        off += 24
        pkt = data[off : off + incl]
        off += incl
        if datalink == DATALINK_HCI_UNENCAP:
            # No H4 byte; bit1 of flags set means command/event, else ACL data.
            if flags & 0x02:
                continue
            pkt = bytes([H4_ACL]) + pkt
        yield ts, flags, pkt


def parse(data: bytes) -> Iterator[AttPacket]:
    # Reassembly buffers per (direction, connection handle).
    partial: dict[tuple[bool, int], tuple[int, bytearray]] = {}
    pending_read: dict[tuple[int], int] = {}
    for ts, flags, pkt in _records(data):
        if not pkt or pkt[0] != H4_ACL or len(pkt) < 5:
            continue
        received = bool(flags & 0x01)
        hdr, acl_len = struct.unpack("<HH", pkt[1:5])
        conn = hdr & 0x0FFF
        pb = (hdr >> 12) & 0x3
        payload = pkt[5 : 5 + acl_len]
        key = (received, conn)
        if pb == 0x01:  # continuation fragment
            if key not in partial:
                continue
            total, buf = partial[key]
            buf.extend(payload)
        else:  # start of an L2CAP PDU
            if len(payload) < 4:
                continue
            l2_len = struct.unpack("<H", payload[:2])[0]
            partial[key] = (l2_len, bytearray(payload))
            total, buf = partial[key]
        if len(buf) < 4 + total:
            continue
        del partial[key]
        l2_len, cid = struct.unpack("<HH", buf[:4])
        if cid != ATT_CID:
            continue
        att = bytes(buf[4 : 4 + l2_len])
        if not att:
            continue
        opcode = att[0]
        if opcode not in ATT_OPCODES:
            continue
        when = datetime(1970, 1, 1) + timedelta(microseconds=ts - BTSNOOP_EPOCH_DELTA_US)
        handle: int | None = None
        value = att[1:]
        if opcode in HANDLE_OPCODES and len(att) >= 3:
            handle = struct.unpack("<H", att[1:3])[0]
            value = att[3:]
        if opcode == 0x0A and handle is not None:
            pending_read[(conn,)] = handle
        if opcode == 0x0B:
            handle = pending_read.pop((conn,), None)
        yield AttPacket(when, received, conn, opcode, handle, value)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--unique", action="store_true", help="list distinct values per (op, handle)")
    ap.add_argument("--handle", type=lambda s: int(s, 0), help="only this attribute handle")
    ap.add_argument("--writes", action="store_true", help="only writes (app -> spa)")
    args = ap.parse_args(argv)

    with open(args.file, "rb") as fh:
        data = fh.read()

    uniques: dict[tuple[str, int | None], dict[bytes, int]] = defaultdict(dict)
    for p in parse(data):
        if args.handle is not None and p.handle != args.handle:
            continue
        if args.writes and p.opcode not in (0x12, 0x52):
            continue
        if args.unique:
            d = uniques[(p.name, p.handle)]
            d[p.value] = d.get(p.value, 0) + 1
            continue
        direction = "spa->app" if p.received else "app->spa"
        h = f"0x{p.handle:04x}" if p.handle is not None else "  -   "
        print(f"{p.time.isoformat(timespec='milliseconds')} {direction} {p.name:9} {h} {p.value.hex(' ')}")
    if args.unique:
        for (name, handle), values in sorted(uniques.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0)):
            h = f"0x{handle:04x}" if handle is not None else "-"
            print(f"== {name} {h}: {len(values)} distinct")
            for value, count in sorted(values.items(), key=lambda kv: -kv[1]):
                print(f"   x{count:<5} {value.hex(' ')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
