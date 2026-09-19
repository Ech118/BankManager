# predictions/ — P2

**Owner: P2.** Rules: [docs/p2/CLAUDE.md](../docs/p2/CLAUDE.md).
Delivered at [roadmap](../docs/roadmap.md) Step 6.

Append-only log of every prediction the system makes, dated and hashed, so it
can be graded when the horizon arrives.

## Why this is the most trustworthy evaluation we have

A backtest can be contaminated by the model's own memory of what happened
([backtest/README.md](../backtest/README.md)). A prediction recorded *today*
about a period that has not happened yet cannot be.

It is slow — the one-year results take a year — but it is the only evaluation
whose validity does not rest on an argument about training data.

## Rules

- **One file per run**: `<date>_<ticker>_<inputhash>.json`
- The input hash covers the factsheet, the metrics and the prompt versions, so a
  later reader can tell whether two predictions came from the same evidence and
  the same pipeline. Without it, a changed prompt silently invalidates every
  comparison.
- **Append-only.** `record()` refuses to overwrite an existing file. A
  prediction log that can be revised is not evidence.
- The log directory is gitignored: the code ships, the records do not.
