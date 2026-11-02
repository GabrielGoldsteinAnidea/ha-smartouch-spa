"""Panel messages and clock (codes from the ACC SmarTouch Digital manuals)."""

import pytest
from spa_core import protocol as p
from spa_core import status
from spa_core.display import DisplayTracker, parse_clock


@pytest.mark.parametrize(
    "text,code",
    [
        ("ECon", "economy"),  # decoded from a real frame, see test_real_frames
        ("CoLd", "cold"),
        ("  0H", "overheat"),  # O and 0 look the same
        ("HLoH", "high_limit"),
        ("HLer", "high_limit"),
        ("5EoP", "sensor_open"),  # S and 5 look the same
        ("5E5H", "sensor_short"),
        ("P5oC", "no_flow_circulation"),
        ("P5oL", "no_flow_low"),
        ("P5oH", "no_flow_high"),
        (" toE", "timeout_error"),
        ("FP1", "programming"),
        ("FP3d", "programming"),
        ("51L", "programming"),
        ("5End", "programming"),
        ("CAnC", "programming"),
        ("U3 1", "programming"),
        ("CALb", "programming"),
    ],
)
def test_classify(text, code):
    assert status.classify(text).code == code


@pytest.mark.parametrize("text", ["", "    ", "102°F", "12:30", "8888", "FIL"])
def test_classify_unknown(text):
    assert status.classify(text) is None


def test_error_codes_are_unique_ids():
    assert "high_limit" in status.ERROR_CODES
    assert len(status.ERROR_CODES) == len(set(status.ERROR_CODES))


def test_parse_clock():
    assert parse_clock("12:30", am=True) == (0, 30)
    assert parse_clock("12:30", am=False) == (12, 30)
    assert parse_clock(" 7:05", am=False) == (19, 5)
    assert parse_clock(" 7:05", am=None) is None  # no AM light state, cannot place it
    assert parse_clock("13:00", am=True) is None
    assert parse_clock("102°F", am=True) is None


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_tracker_messages_expire_and_rank():
    clk = Clock()
    tr = DisplayTracker(clock=clk)
    tr.update("ECon")
    tr.update(" 98°F")
    assert tr.status().code == "economy" and tr.state.water_temp.value == 98
    clk.t += 30
    tr.update("P5oL")
    assert tr.status().code == "no_flow_low"  # errors outrank economy
    assert [m.code for m in tr.current_errors()] == ["no_flow_low"]
    clk.t += 120
    assert tr.status() is None and tr.current_messages() == []


def test_tracker_clock_estimate():
    clk = Clock()
    tr = DisplayTracker(clock=clk)
    frame = p.parse_display(p.encode_display("1159", dots=(False, True, True, False), leds=bytes([0x80, 0])))
    tr.update(frame.text, frame.indicators)
    assert tr.state.clock == (11, 59)
    clk.t += 125
    assert tr.estimated_clock() == (12, 1)


def test_real_frames():
    """Display frames from a real SmarTouch spa (diagnostics, 2026-11-02). No PIN or MAC in them."""
    water = p.parse_display(bytes.fromhex("f17f6f000000"))
    assert water.text == " 98°F" and water.unit == "F"
    econ = p.parse_display(bytes.fromhex("545c39790000"))
    assert econ.text == "ECon" and status.classify(econ.text).code == "economy"
    after_light = p.parse_display(bytes.fromhex("f17f6f000110"))
    assert after_light.indicators["light"] and after_light.indicators["heating"]
