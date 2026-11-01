import pytest
from spa_core.seven_segment import SegmentMap, SevenSegmentDecoder


def test_standard_digits_roundtrip():
    dec = SevenSegmentDecoder()
    # Standard gfedcba encodings of 0-9.
    assert dec.decode(bytes([0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F])) == "0123456789"


def test_letters_and_dp():
    dec = SevenSegmentDecoder()
    assert dec.decode(dec.encode("FIL")) == "F1L"  # I is indistinguishable from 1
    assert dec.decode(bytes([0x06 | 0x80, 0x00])) == "1. "
    assert dec.decode(bytes([0x49])) == "?"  # a+d+g: not a known glyph


def test_custom_bit_order():
    m = SegmentMap.from_order("gfedcba.")  # reversed: bit0=g
    dec = SevenSegmentDecoder(m)
    assert dec.decode(dec.encode("104F")) == "104F"
    assert dec.encode("1") == bytes([0b0110000])  # b=bit5, c=bit4


@pytest.mark.parametrize("bad", ["abcdef", "abcdefgz", "abcdeff."])
def test_invalid_orders(bad):
    with pytest.raises(ValueError):
        SegmentMap.from_order(bad)
