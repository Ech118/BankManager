#!/usr/bin/env python3
"""Regenerate schema/*.json from the pydantic models. Run with `make gen-schema`.

The models in schema/contracts/ are authoritative. Never hand-edit the JSON:
tests/contracts/test_schema_export.py fails the build if they drift apart.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schema.contracts.export import write_all  # noqa: E402


def main() -> int:
    written = write_all()
    for path in written:
        print(f"wrote {path.relative_to(ROOT)}")
    print(f"{len(written)} schema files regenerated from schema/contracts/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
