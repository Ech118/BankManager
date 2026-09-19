# backtest/ — P2

You are working in **P2**. Full rules: [docs/p2/CLAUDE.md](../docs/p2/CLAUDE.md).

- **May import:** `schema.contracts`, `calc/`, `orchestrator.api`
- Runs through `orchestrator.api.run_analysis` like any live run, so a backtest
  exercises the real pipeline rather than a parallel one that could drift.

Two rules that are not negotiable in the demo:

1. Grade on **excess return over the index**, never absolute return.
2. A calibration chart below **100** tickers is stamped `ILLUSTRATIVE` *in the
   image*, not just in the caption.

The model may already remember what happened to these companies. Say which
defence was used — point-in-time data, anonymization, or the forward log — and
do not overstate what the result shows.
