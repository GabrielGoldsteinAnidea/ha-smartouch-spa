import struct

from btsnoop_att import BTSNOOP_EPOCH_DELTA_US, parse


def record(payload: bytes, received: bool, ts_us: int) -> bytes:
    pkt = b"\x02" + payload
    return struct.pack(">IIIIq", len(pkt), len(pkt), 1 if received else 0, 0, ts_us) + pkt


def acl(conn: int, pb: int, data: bytes) -> bytes:
    return struct.pack("<HH", conn | (pb << 12), len(data)) + data


def l2cap_att(att: bytes) -> bytes:
    return struct.pack("<HH", len(att), 0x0004) + att


def test_parse_write_and_fragmented_notify():
    ts = BTSNOOP_EPOCH_DELTA_US + 1_000_000
    write = acl(0x40, 0, l2cap_att(b"\x52\x12\x00\xaa\x01"))  # WRITE_CMD h=0x12
    notify = l2cap_att(b"\x1b\x15\x00" + bytes(range(30)))
    frag1 = acl(0x40, 2, notify[:20])
    frag2 = acl(0x40, 1, notify[20:])
    other = acl(0x40, 2, struct.pack("<HH", 2, 0x0005) + b"\x00\x00")  # signalling, ignored
    data = b"btsnoop\x00" + struct.pack(">II", 1, 1002)
    data += record(write, False, ts) + record(frag1, True, ts + 1) + record(frag2, True, ts + 2)
    data += record(other, True, ts + 3)

    pkts = list(parse(data))
    assert [(p.name, p.handle, p.received) for p in pkts] == [("WRITE_CMD", 0x12, False), ("NOTIFY", 0x15, True)]
    assert pkts[0].value == b"\xaa\x01"
    assert pkts[1].value == bytes(range(30))
    assert pkts[0].time.year == 1970
