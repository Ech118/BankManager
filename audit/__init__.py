"""P2: the verification gate. Public interface: audit/api.py.

Specified by docs/verification.md and docs/adr/0005.

Reads a ResearchState and a Factsheet, and nothing else. Its two external needs
are injected as callables - `get_text` for filing text, `verify_claim` for the
one LLM check - so audit/ imports neither data/ nor any model SDK.
"""
