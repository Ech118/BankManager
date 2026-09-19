# mcp_server/ — P1

You are working in **P1**. Full rules: [docs/p1/CLAUDE.md](../docs/p1/CLAUDE.md).

- **May import:** `schema.contracts`, `data/` — and `calc.api` in
  `tools/calculate_valuation.py` **only**
- **May NOT:** contain a single formula

`tools/calculate_valuation.py` is the one sanctioned cross-partition import in
the repo ([ADR 0007](../docs/adr/0007-partition-boundaries.md)). It is a
pass-through. Arithmetic appearing in any tool module is a defect — it belongs
in `calc/`.

All tools are read-only. Do not add a tool that writes.
