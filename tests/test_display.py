from spa_core.display import DisplayTracker, Unit, parse_temperature


def test_parse_temperature():
    assert parse_temperature("102F").value == 102
    assert parse_temperature("102F").unit is Unit.F
    assert parse_temperature(" 39C").unit is Unit.C
    assert parse_temperature("102").unit is None
    assert parse_temperature("FIL") is None
    assert parse_temperature("200F") is None  # implausible
    assert parse_temperature("50C") is None


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_tracker_separates_setpoint_from_water_temp():
    clk = Clock()
    tr = DisplayTracker(setpoint_window=5, clock=clk)
    tr.update("100F")
    assert tr.state.water_temp.value == 100 and tr.state.set_point is None
    tr.note_temp_button_press()
    clk.t = 1
    tr.update("104F")
    tr.update("    ")  # flashing
    assert tr.state.set_point.value == 104
    assert tr.state.water_temp.value == 100
    clk.t = 7
    tr.update("101F")
    assert tr.state.water_temp.value == 101 and tr.state.set_point.value == 104
    tr.update("FIL")
    assert tr.state.status_text == "FIL" and tr.state.water_temp.value == 101
