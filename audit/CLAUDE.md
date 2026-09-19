# audit/ — P2

You are working in **P2**. Full rules: [docs/p2/CLAUDE.md](../docs/p2/CLAUDE.md).

- **May import:** `schema.contracts` only
- **May NOT import:** `data/`, any LLM SDK, or any other partition

Both external needs are **injected**: `get_text` for filing text, `verify_claim`
for the one LLM check. That is what keeps the whole gate testable with two
stubs — do not replace either with a direct import.

Reads a `ResearchState` and a `Factsheet`, and nothing else.

Keep the LLM check list at **one** entry. A verifier that hallucinates is worse
than none, because it launders a bad claim as checked
([ADR 0005](../docs/adr/0005-deterministic-verification-gate.md)).
