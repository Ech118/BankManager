"""P2-owned test setup (mirrors tests/contracts/conftest.py's sys.path pattern,
scoped to calc/ so it stays inside our ownership boundary, plan.txt 15.4)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Reuse the frozen schema-validation helper (tests/contracts/helpers.py) as a
# read-only utility - we import it, we never edit it.
_CONTRACTS = ROOT / "tests" / "contracts"
if str(_CONTRACTS) not in sys.path:
    sys.path.insert(0, str(_CONTRACTS))
