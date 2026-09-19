"""P1 storage: Postgres, used only when MODE=live.

Specified by docs/data-model.md "Storage" and docs/adr/0006.

Mock mode never touches this package. The fixture-backed repositories in
data/repositories/ satisfy the same Protocols, so P2 and P3 develop and test
with no database running at all (decision 6).

Search is Postgres full-text, scoped by ticker, form, item and date. That is a
deliberate starting point, not a placeholder for embeddings: scoped keyword
search over structurally-parsed sections is inspectable and reproducible.
"""
