"""Codec tests.

Expected values are derived by hand from the app's JavaScript
(com.mltech.agi.accslv2a 1.1.2, see docs/PROTOCOL.md). They are NOT
captured frames: no spa traffic has been captured yet. Replace or extend
them with real captures (PIN and MAC redacted) once Step 4 is done.
"""

import pytest
from spa_core import protocol as p


def test_key_codes_match_app_buttons_codes():
    # js/panel.js buttons_codes
    assert {k.value: p.encode_key(k) for k in p.Key} == {
        "light": b"l0",
        "jets": b"j0",
        "aux": b"a0",
        "aux2": b"x0",
        "system": b"s0",
        "up": b"u0",
        "down": b"d0",
        "set_temp": b"u1",
        "set_time": b"d1",
    }


@pytest.mark.parametrize(
    "value,unit,expected",
    [
        (102, "F", b"102F"),
        (99, "F", b"099F"),  # ('000' + 99 + 'F').slice(-4)
        (40, "F", b"040F"),
        (104, "F", b"104F"),
        (38.9, "C", b"389C"),  # f2c(102)
        (40.0, "C", b"400C"),  # f2c(104)
        (4.8, "C", b"048C"),  # f2c(40)
    ],
)
def test_encode_temperature_like_app(value, unit, expected):
    assert p.encode_temperature(value, unit) == expected


@pytest.mark.parametrize("value,unit", [(105, "F"), (39, "F"), (101.5, "F"), (38.5, "C"), (41.0, "C"), (100, "K")])
def test_encode_temperature_rejects_values_app_never_sends(value, unit):
    with pytest.raises(ValueError):
        p.encode_temperature(value, unit)


def test_app_celsius_values():
    # panel.f2c: odd F -> (f-1)*11/2-166 tenths, even F -> f*11/2-172 tenths
    assert p.f_to_c_app(104) == 40.0
    assert p.f_to_c_app(101) == 38.4
    assert p.f_to_c_app(102) == 38.9
    assert len(p.APP_CELSIUS_VALUES) == 65
    assert p.nearest_app_celsius(38.5) == 38.4
    assert p.nearest_app_celsius(50) == 40.0


def test_splitter_matches_app():
    assert p.split_ble_string("a" * 19) == ["a" * 19]
    assert p.split_ble_string("a" * 20) == ["0" + "a" * 19, "9a"]
    assert p.split_ble_string("a" * 40) == ["0" + "a" * 19, "2" + "a" * 19, "9" + "a" * 2]


def test_auth_writes():
    mcode = "ABCDEFGHIJKLMNOP"  # 16 chars, like RandomBase64url()
    assert p.auth_writes(mcode, "1234") == [b"0ABCDEFGHIJKLMNOP123", b"94"]
    with pytest.raises(ValueError):
        p.auth_writes(mcode, "12a4")
    with pytest.raises(ValueError):
        p.auth_writes(mcode, "123")


def test_generate_mcode():
    a, b = p.generate_mcode(), p.generate_mcode()
    assert len(a) == 16 and a != b
    assert set(a) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def test_display_byte0_is_rightmost_and_unit_detection():
    # The app treats a first byte of f1 (F + dot) as degrees F, b9 (C + dot) as C.
    frame = p.parse_display(bytes([0xF1, 0x5B, 0x3F, 0x06, 0x00, 0x00]))
    assert frame.text == "102°F"
    assert frame.unit == "F"
    frame = p.parse_display(bytes([0xB9, 0x6D, 0xFF, 0x4F, 0x00, 0x00]))  # 3, 8., 5, °C
    assert frame.text == "38.5°C"
    assert frame.unit == "C"


def test_display_clock_colon():
    data = p.encode_display("1230", dots=(False, True, True, False))
    assert p.parse_display(data).text == "12:30"


def test_display_indicators():
    data = bytes([0xF1, 0x5B, 0x3F, 0x06, 0b0001_0001, 0b0001_0000])
    leds = p.parse_display(data).indicators
    assert leds["heating"] and leds["filtering"] and leds["light"]
    assert not any(v for k, v in leds.items() if k not in {"heating", "filtering", "light"})


def test_display_ignores_low_nibble_of_byte5_and_wrong_length():
    leds = p.parse_display(bytes([0, 0, 0, 0, 0, 0x0F])).indicators
    assert not any(leds.values())
    assert p.parse_display(b"\x00" * 5) is None
    assert p.parse_display(b"\x00" * 7) is None


def test_encode_display_roundtrip():
    data = p.encode_display(" 99F", dots=(False, False, False, True))
    assert data[0] == 0xF1  # rightmost glyph first
    assert p.parse_display(data).text == " 99°F"


def test_protected_characteristics():
    assert p.CHAR_MMODE in p.PROTECTED_CHARS
    assert p.CHAR_KEYBOARD not in p.PROTECTED_CHARS


@pytest.mark.parametrize(
    "hour,minute,expected",
    [(19, 45, b"0745P"), (0, 5, b"1205A"), (12, 0, b"1200P"), (9, 30, b"0930A"), (23, 59, b"1159P")],
)
def test_encode_time_like_app(hour, minute, expected):
    # panel.js send-time-value -> toLocaleString(en-US, hour12) -> transmitter.parse_time
    assert p.encode_time(hour, minute) == expected


@pytest.mark.parametrize("hour,minute", [(24, 0), (-1, 0), (12, 60)])
def test_encode_time_rejects_invalid(hour, minute):
    with pytest.raises(ValueError):
        p.encode_time(hour, minute)


def test_key_leds_cover_device_keys():
    assert set(p.KEY_LEDS) == {p.Key.JETS, p.Key.AUX, p.Key.AUX2}
    for lo, hi in p.KEY_LEDS.values():
        assert lo in p.INDICATOR_BITS and hi in p.INDICATOR_BITS
