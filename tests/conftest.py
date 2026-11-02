import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPA_CORE = ROOT / "custom_components" / "smartouch_spa" / "spa_core"

# Import spa_core as a top-level package so tests don't need Home Assistant.
# Register just that package: putting the integration folder itself on
# sys.path would let its select.py and time.py shadow the standard library.
if "spa_core" not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        "spa_core", SPA_CORE / "__init__.py", submodule_search_locations=[str(SPA_CORE)]
    )
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["spa_core"] = _mod
    _spec.loader.exec_module(_mod)

sys.path.insert(0, str(ROOT / "tools" / "analysis"))
