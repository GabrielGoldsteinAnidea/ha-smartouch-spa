import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Import spa_core as a top-level package so tests don't need Home Assistant.
sys.path.insert(0, str(ROOT / "custom_components" / "smartouch_spa"))
sys.path.insert(0, str(ROOT / "tools" / "analysis"))
