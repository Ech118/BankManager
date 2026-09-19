"""P2-owned test setup (mirrors calc/tests/conftest.py, plan.txt 15.4)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
