"""The shared contract location.

`schema/contracts/` holds the pydantic models that are the SOURCE OF TRUTH for
every cross-partition shape. The `schema/*.json` files beside it are GENERATED
from those models by `make gen-schema`.

Changing anything in here is a CONTRACT-CHANGE PR requiring approval from all
three partitions plus a `schema/CHANGELOG.md` entry (CONTRIBUTING.md).
"""
