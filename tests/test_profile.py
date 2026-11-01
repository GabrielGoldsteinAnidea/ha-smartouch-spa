from spa_core.profile import Button, ProtocolProfile, parse_hex


def test_parse_hex_formats():
    assert parse_hex("aa 01 FF") == parse_hex("aa01ff") == parse_hex("aa:01:ff") == b"\xaa\x01\xff"


def test_default_is_discovery_mode():
    p = ProtocolProfile()
    assert not p.can_read_display
    assert not p.can_press(Button.LIGHT)
    assert p.extract_display(b"\x01\x02") is None


def test_extract_display():
    p = ProtocolProfile(notify_uuid="x", display_prefix=b"\xa5", display_offset=2, display_length=3)
    assert p.extract_display(b"\xa5\x00\x06\x3f\x66\x00") == b"\x06\x3f\x66"
    assert p.extract_display(b"\x00\x00\x06\x3f\x66") is None  # wrong prefix
    assert p.extract_display(b"\xa5\x00\x06") is None  # too short
