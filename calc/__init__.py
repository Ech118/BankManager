"""P2: the deterministic compute engine. Public interface: calc/api.py.

PURE (docs/adr/0001, docs/adr/0007): no network, no database, no LLM. Given the
same inputs this package returns the same outputs, every time, which is what
makes the verifier's recompute check meaningful.

Every number the reader ever sees is produced here or in audit/.
"""
