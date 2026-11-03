"""Menu layout, passive capture and equipment detection.

The replay below is the display sequence from the owner's spa on 2026-11-02
(Home Assistant history of the Display sensor), while the owner scrolled the
parameter menu and then the options menu at the panel. The Edit light
blinked throughout; here it is simply on.
"""

import itertools

from spa_core import equipment as eq
from spa_core import menus

PARAM_SCROLL = "FP1 ,CAnC,5End,PUF ,Uto ,CHCL,ECL ,CLdn,FP4d,FP3d,FP2d,FP1d,FP4 ,FP3 ,FP2 ,FP1 ,CAnC".split(",")
OPTION_SCROLL = [
    "CAnC",
    "5End",
    *(f"U{i} 0" for i in range(1, 9)),
    "P1 1",
    "P2 1",
    "P3 0",
    "P4 0",
    "P5 0",
    "P6 0",
    "P7 0",
    "P8 1",
    *(f"d{i}  " for i in range(1, 9)),
    "CAnC",
]
EDIT = {"edit": True, "heating": True}
IDLE = {"edit": False, "heating": True}


def replay(tracker, texts, t0=0.0):
    t = t0
    for text in texts:
        t += 0.5
        tracker.update(text, EDIT, t)
    return t


def test_real_scroll_matches_menu_order():
    # Scrolling went backwards through the circular menus.
    labels = [menus.parse_label(x).code for x in PARAM_SCROLL]
    for a, b in itertools.pairwise(labels):
        assert menus.neighbours(menus.Menu.PARAMETERS, a)[1] == b
    labels = [menus.parse_label(x).code for x in OPTION_SCROLL]
    for a, b in itertools.pairwise(labels):
        assert menus.neighbours(menus.Menu.OPTIONS, a)[0] == b


def test_capture_from_real_session():
    commits = []
    tr = menus.MenuTracker(on_commit=commits.append)
    t = replay(tr, PARAM_SCROLL)
    assert tr.open and tr.menu is menus.Menu.PARAMETERS and tr.label.code == "CAnC"
    tr.update("104°F", IDLE, t + 0.2)  # still within the Edit hold time
    tr.update("103°F", IDLE, t + 3)
    assert not tr.open
    assert commits == []  # only labels were shown, no values
    t = replay(tr, OPTION_SCROLL, t + 5)
    assert tr.menu is menus.Menu.OPTIONS
    tr.check_timeout(t + 5)
    assert not tr.open
    (values,) = commits
    assert values["P1"] == 1 and values["P2"] == 1 and values["P8"] == 1
    assert values["P6"] == 0 and all(values[f"U{i}"] == 0 for i in range(1, 9))
    assert "d1" not in values  # d labels carry no value


def test_equipment_from_real_options():
    captured = {"P1": 1, "P2": 1, "P3": 0, "P6": 0, "P7": 0, "P8": 1}
    e = eq.resolve("auto", "auto", "auto", captured.get)
    assert e == eq.Equipment(eq.Jets1.SINGLE, eq.Jets2.TWO, eq.Air.YES)
    # The owner's blower is enabled in the controller but not fitted.
    assert eq.resolve("auto", "auto", "no", captured.get).air is eq.Air.NO
    # Nothing captured yet: the manual's defaults (P2=0, P7=0, P8=0, P6=0).
    assert eq.resolve("auto", "auto", "auto", {}.get) == eq.Equipment(eq.Jets1.DUAL, eq.Jets2.SINGLE, eq.Air.YES)


def test_edits_kept_only_when_saved():
    commits = []
    tr = menus.MenuTracker(on_commit=commits.append)
    # U3 shown as 0, toggled to 1, then CAnC: the controller keeps 0.
    replay(tr, ["U3 0", "U3 1", "CAnC"])
    tr.check_timeout(100)
    assert commits[-1] == {"U3": 0}
    # Same, but saved with SEnd: the controller now has 1.
    t = replay(tr, ["U3 0", "U3 1", "5End"], 200)
    tr.update("104°F", IDLE, t + 3)
    assert commits[-1] == {"U3": 1}


def test_value_screens():
    commits = []
    tr = menus.MenuTracker(on_commit=commits.append)
    t = replay(tr, ["FP1d", "  60", "    ", "  60", "FP1d", "FP1 "])
    tr.update(" 8:30", {"edit": True, "am": True}, t + 0.5)
    tr.update("  :30", {"edit": True, "am": True}, t + 1.0)  # hour flashing
    tr.update("FP1 ", EDIT, t + 1.5)
    tr.check_timeout(t + 10)
    assert commits[-1] == {"FP1d": 60, "FP1": "08:30"}


def test_settings_table():
    assert menus.PARAMETER_ORDER[0] == "FP1" and menus.PARAMETER_ORDER[-2:] == ("SEnd", "CAnC")
    assert not menus.SETTINGS["P8"].writable and not menus.SETTINGS["U7"].writable
    assert menus.SETTINGS["U1"].writable and menus.SETTINGS["Uto"].max == 60
    assert menus.parse_label("Uto ").code == "Uto" and menus.parse_label("5End").code == "SEnd"
    assert menus.parse_label("  60") is None and menus.parse_label("104°F") is None
