import sys
from pathlib import Path

# Import mvg.py directly so tests don't need Home Assistant installed.
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "mvg_commute"))
