"""Seven-segment display decoding.

The SmarTouch app mirrors the spa keypad's LED display. Each digit is most
likely transmitted as one byte with one bit per segment, but the bit order
used by the ACC controller has NOT been confirmed yet (see docs/PROTOCOL.md).
The bit order is therefore a parameter, defaulting to the most common
convention (bit0=a ... bit6=g, bit7=dp).

Segment naming (standard):

     aaa
    f   b
    f   b
     ggg
    e   c
    e   c
     ddd  .dp
"""

from __future__ import annotations

from dataclasses import dataclass

SEGMENTS = "abcdefg"

# Character -> set of lit segments. Covers digits and the letters that are
# legible on a 7-segment display and commonly used by spa controllers
# (e.g. "FIL", "OH", "Er", "SL", "Std", "PrH").
_GLYPHS: dict[str, str] = {
    "0": "abcdef",
    "1": "bc",
    "2": "abdeg",
    "3": "abcdg",
    "4": "bcfg",
    "5": "acdfg",
    "6": "acdefg",
    "7": "abc",
    "8": "abcdefg",
    "9": "abcdfg",
    "A": "abcefg",
    "b": "cdefg",
    "C": "adef",
    "c": "deg",
    "d": "bcdeg",
    "E": "adefg",
    "F": "aefg",
    "H": "bcefg",
    "h": "cefg",
    "J": "bcde",
    "L": "def",
    "n": "ceg",
    "o": "cdeg",
    "P": "abefg",
    "r": "eg",
    "t": "defg",
    "U": "bcdef",
    "u": "cde",
    "y": "bcdfg",
    "-": "g",
    "_": "d",
    " ": "",
}
# Note: "S" and "5", "I" and "1", "O" and "0", "G" and "6" are identical on a
# 7-segment display. We decode to the digit; callers interpret by context.
_ENCODE_ALIASES = {"I": "1", "O": "0", "S": "5", "G": "6"}


@dataclass(frozen=True)
class SegmentMap:
    """Maps segment letters (a-g, dp) to bit positions within a digit byte."""

    a: int = 0
    b: int = 1
    c: int = 2
    d: int = 3
    e: int = 4
    f: int = 5
    g: int = 6
    dp: int | None = 7

    @classmethod
    def from_order(cls, order: str) -> SegmentMap:
        """Build from a string listing segments from bit0 upward, e.g. "abcdefg.".

        A "." marks the decimal-point bit. Use "x" for unused bits.
        """
        positions: dict[str, int] = {}
        for bit, seg in enumerate(order):
            if seg == ".":
                positions["dp"] = bit
            elif seg in SEGMENTS:
                positions[seg] = bit
            elif seg != "x":
                raise ValueError(f"invalid segment {seg!r} in order {order!r}")
        missing = set(SEGMENTS) - positions.keys()
        if missing:
            raise ValueError(f"segment order {order!r} is missing {sorted(missing)}")
        positions.setdefault("dp", None)
        return cls(**positions)

    def bit(self, segment: str) -> int:
        return getattr(self, segment)


DEFAULT_SEGMENT_MAP = SegmentMap()


def _build_table(seg_map: SegmentMap) -> dict[int, str]:
    table: dict[int, str] = {}
    for char, segs in _GLYPHS.items():
        value = 0
        for seg in segs:
            value |= 1 << seg_map.bit(seg)
        # First glyph wins for ambiguous patterns (digits are listed first).
        table.setdefault(value, char)
    return table


@dataclass(frozen=True)
class DecodedDigit:
    char: str  # "?" if the pattern is not a known glyph
    dp: bool
    raw: int


class SevenSegmentDecoder:
    def __init__(self, seg_map: SegmentMap = DEFAULT_SEGMENT_MAP) -> None:
        self._map = seg_map
        self._table = _build_table(seg_map)
        self._dp_mask = 0 if seg_map.dp is None else 1 << seg_map.dp

    def decode_digit(self, raw: int) -> DecodedDigit:
        dp = bool(raw & self._dp_mask)
        char = self._table.get(raw & ~self._dp_mask & 0xFF, "?")
        return DecodedDigit(char=char, dp=dp, raw=raw)

    def decode(self, data: bytes) -> str:
        """Decode a sequence of digit bytes into display text.

        A lit decimal point is rendered as "." after its digit.
        """
        out = []
        for raw in data:
            digit = self.decode_digit(raw)
            out.append(digit.char)
            if digit.dp:
                out.append(".")
        return "".join(out)

    def encode(self, text: str) -> bytes:
        """Inverse of decode (no decimal points). Mainly for tests/simulation."""
        result = bytearray()
        for char in text:
            char = _ENCODE_ALIASES.get(char, char)
            if char not in _GLYPHS:
                raise ValueError(f"cannot encode {char!r}")
            value = 0
            for seg in _GLYPHS[char]:
                value |= 1 << self._map.bit(seg)
            result.append(value)
        return bytes(result)
