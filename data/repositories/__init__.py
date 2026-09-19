"""P1 repositories: the concrete implementations of the contracts' Protocols.

Specified by schema/contracts/interfaces.py and docs/data-model.md.

Two implementations of each Protocol, chosen by MODE:
  postgres_*.py   MODE=live  - the real store
  fixture_*.py    MODE=mock  - the ACME fixtures, in memory, no database

Because both satisfy the same Protocol, nothing above this layer knows or cares
which is in use. That is what keeps mock mode honest: it exercises the same call
paths rather than a shortcut around them.
"""
