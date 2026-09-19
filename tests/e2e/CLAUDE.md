# tests/e2e/ — P3

You are working in **P3**. Full rules: [docs/p3/CLAUDE.md](../../docs/p3/CLAUDE.md).

Each test corresponds to a checkpoint in
[docs/roadmap.md](../../docs/roadmap.md), so a step being "done" has a
definition rather than an opinion.

Two tests are not about features and must never be deleted:

- **prompt injection** — a planted instruction inside a filing section must not
  move the verdict
- **disclaimer present** — cheap, and it is the one thing that must never
  regress

`tests/contracts/` is shared and frozen; only `tests/e2e/` belongs to P3.
