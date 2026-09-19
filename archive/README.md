# archive/

Superseded material. **Nothing here is deleted** — it is kept because the record
of why something was decided is what makes it safe to change later.

Nothing in this directory is loaded, imported or linted. It is context only.

---

## Contents

### `plan.txt`

The original planning document, written before the Step 0 restructure. It
contains the project's origin story, the fifteen-section investment-committee
prompt it grew out of, and — most valuably — a numbered review of that
approach's flaws.

**Superseded by:** [ARCHITECTURE.md](../ARCHITECTURE.md), [docs/](../docs/), and
[CLAUDE.md](../CLAUDE.md).

**Why archived:** after the restructure, most of §4–15 described an architecture
the repo no longer has. Two conflicting sources of truth is exactly the failure
mode this project is built to avoid, so the still-valid content was carried
forward and the document was retired.

---

## Where each flaw from `plan.txt` now lives

The flaws labelled A–M in `plan.txt` §13, and the numbered review in §3, were
the most useful part of that document. Every one is carried forward:

| Flaw | Original concern | Now lives in |
|---|---|---|
| **A** | Backtest contaminated by the model's own memory — called the biggest flaw | [ADR 0003](../docs/adr/0003-point-in-time-correctness.md) · [sec-pitfalls §1](../docs/sec-pitfalls.md) · [backtest/README.md](../backtest/README.md) · [predictions/README.md](../predictions/README.md) |
| **B** | Calibration on a handful of tickers is meaningless | [roadmap Step 6](../docs/roadmap.md) · `backtest/calibration.py` (`MIN_N_FOR_CALIBRATION`) |
| **C** | P(beat S&P) derived from LLM-guessed probabilities | [ADR 0001](../docs/adr/0001-code-computes-llm-interprets.md) · [pipeline §6](../docs/pipeline.md) · `calc/config.py` (`BASE_RATE_P_BEAT_SP500`, `PRIOR_SHIFT_CAP`, `SCENARIO_WEIGHT_BAND`) |
| **D** | Reverse DCF dominated by assumptions | [ADR 0001](../docs/adr/0001-code-computes-llm-interprets.md) · `calc/config.py` sensitivity axes · `ReverseDcf.sensitivity_grid` is required and non-empty |
| **E** | Weak, free-tier market data | [sec-pitfalls §8](../docs/sec-pitfalls.md) · [data-model.md](../docs/data-model.md) (`unavailable`, `data_quality`) · `calc/valuation/peers.py` (usable peer count) |
| **F** | Prompt injection from filings and news | [verification.md](../docs/verification.md) · `prompts/shared_rules.md` rule 4 · read-only MCP tools · the injection test in `tests/e2e/` |
| **G** | Secrets in a public repo | `.gitignore`, `.env.example`, `scripts/secret_scan.sh`, the pre-commit hook, and the CI secret scan |
| **H** | Sector scope — banks, REITs, pre-revenue | `data/normalize/scope.py` (`EXCLUDED_SIC_RANGES`) · [p1/README.md](../docs/p1/README.md) |
| **I** | Unverifiable qualitative claims | [ADR 0002](../docs/adr/0002-financial-truth-layer.md) · [ADR 0005](../docs/adr/0005-deterministic-verification-gate.md) · the `Claim` model · `unsupported_claim` |
| **J** | Error propagation between agents | [pipeline §5](../docs/pipeline.md) — the Red Team gets the RAW fact sheet · `cross_agent_contradiction` |
| **K** | Cost and latency of ~7 LLM calls | [mcp-tools.md](../docs/mcp-tools.md) "Cost" · per-agent tool sets · accession-keyed cache · targeted retries · `orchestrator/events.py` token logging |
| **L** | Schema drift | [ADR 0002](../docs/adr/0002-financial-truth-layer.md) · `schema/contracts/` as source of truth · `test_schema_export.py` · [CONTRIBUTING.md](../CONTRIBUTING.md) contract-change process |
| **M** | Output reads like investment advice | `Verdict.disclaimer` (required, min length) · `orchestrator/report/generator.py` · a test in `tests/e2e/` |

And the numbered review from `plan.txt` §3:

| # | Concern | Now lives in |
|---|---|---|
| 1 | One prompt asking for fifteen sections at once | [pipeline.md](../docs/pipeline.md) — a staged pipeline |
| 2 | "Use current market data" when the model has none | [ADR 0002](../docs/adr/0002-financial-truth-layer.md), [ADR 0003](../docs/adr/0003-point-in-time-correctness.md) |
| 3 | LLM doing arithmetic | [ADR 0001](../docs/adr/0001-code-computes-llm-interprets.md) |
| 4 | Unanchored probabilities and 1-10 scores | `calc/scenarios/prior.py`, `calc/scenarios/rubric.py` |
| 5 | "Take a position" biases toward BUY | the Red Team, and the Synthesizer's obligation to answer it |
| 6 | FACT/ESTIMATE/ASSUMPTION only requested, never enforced | the `ValueObject` `type` field and its validators |
| 7 | Verdict last, sections overlapping | [ADR 0004](../docs/adr/0004-report-rendered-from-research-state.md) — card first |
| 8 | Expectations vs reality was only prose | `calc/valuation/reverse_dcf.py` + the `expectations` section |
| 9 | No validation | [ADR 0005](../docs/adr/0005-deterministic-verification-gate.md) |
| 10 | No disclaimer | `Verdict.disclaimer`, required and tested |

### Conventions

The conventions from `plan.txt` §15.6 — fractions not percents, full USD, ISO
dates, `unavailable` never `0`, sign conventions, source-id formats — are now in
[CLAUDE.md §4](../CLAUDE.md) and [docs/data-model.md](../docs/data-model.md),
and are enforced by model validators plus `tests/contracts/test_value_rules.py`.

### The partition plan

`plan.txt` §15 described the three-way partition. The partitions are **unchanged**;
the plan is now in [ADR 0007](../docs/adr/0007-partition-boundaries.md),
[CONTRIBUTING.md](../CONTRIBUTING.md) and the `docs/pN/` directories.

---

## What is NOT archived

The v1.0.0 hand-written `schema/*.json` files were **not** moved here. They
remain at `schema/*.json`, now regenerated from `schema/contracts/`. The
pre-restructure versions are in git history at tag `step0`, and the change is
recorded in [schema/CHANGELOG.md](../schema/CHANGELOG.md).

The ACME fixtures were extended in place rather than replaced, so every number a
human hand-checked at Step 0 still holds.
