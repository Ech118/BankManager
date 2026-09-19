# BankManager — instructions for every Claude instance

AI equity-research tool. A user enters a ticker; the system produces a research
report and a verdict on whether the stock is expected to beat the S&P 500 over
0-12 months, 1-3 years and 3-5 years.

Three people build this repo at the same time, each with their own Claude, each
on **one partition**. Follow these rules exactly.

**Read before writing any code:** [ARCHITECTURE.md](ARCHITECTURE.md),
[docs/pipeline.md](docs/pipeline.md), and your partition's
`docs/pN/CLAUDE.md`.

---

## 1. Find out which partition you are

Your person will say P1, P2 or P3. **If they have not, ASK. Do not guess.**

| Partition | Name | May edit ONLY |
|---|---|---|
| **P1** | Data & MCP | `data/` `mcp_server/` `fixtures/real/` `docs/p1/` |
| **P2** | Calc, audit & eval | `calc/` `audit/` `backtest/` `predictions/` `docs/p2/` |
| **P3** | Agents, orchestrator & web | `agents/` `prompts/` `orchestrator/` `web/` `tests/e2e/` `docs/p3/` |

Everything else is **read-only** for you: `schema/`, `fixtures/mock/`,
`tests/contracts/`, `scripts/`, `Makefile`, `.gitignore`, `.env.example`,
`ruff.toml`, `README.md`, `.github/`, `archive/`, and the other partitions'
directories.

**The one exception:** you may ADD a new file in `docs/requests/`. Never edit an
existing one.

Full rules for your partition: [docs/p1/CLAUDE.md](docs/p1/CLAUDE.md) ·
[docs/p2/CLAUDE.md](docs/p2/CLAUDE.md) · [docs/p3/CLAUDE.md](docs/p3/CLAUDE.md)

---

## 2. The six principles

Everything below follows from these. Each has an
[ADR](docs/adr/) with the reasoning and the costs.

1. **Code computes, the LLM interprets.** No agent ever produces a number by
   doing arithmetic. All metrics and valuation math are deterministic code in
   `calc/`. ([ADR 0001](docs/adr/0001-code-computes-llm-interprets.md))

2. **Financial truth layer.** Every number lives in a normalized facts store
   with provenance, and agents cite `fact_id`s, never bare numbers.
   ([ADR 0002](docs/adr/0002-financial-truth-layer.md))

3. **Point-in-time correctness.** Every data query takes an `as_of` date and
   returns only data filed or observed before it.
   ([ADR 0003](docs/adr/0003-point-in-time-correctness.md))

4. **The report is rendered from a structured `ResearchState` object**, never
   from free-form agent text.
   ([ADR 0004](docs/adr/0004-report-rendered-from-research-state.md))

5. **The verification gate is mostly deterministic code**, plus LLM checks only
   for qualitative claims. Retries are targeted to the owning section and
   capped; after the cap, the report ships with failed claims marked unverified.
   ([ADR 0005](docs/adr/0005-deterministic-verification-gate.md))

6. **No naive chunk-and-embed RAG.** Filings are parsed by structure (10-K/10-Q
   Items, notes), and search starts as Postgres full-text search scoped by
   ticker, form, item and date.
   ([ADR 0006](docs/adr/0006-no-naive-chunk-and-embed-rag.md))

---

## 3. Boundary rules

- **Never implement outside your partition.** Need something from another
  partition? Add `docs/requests/YYYY-MM-DD-pX-to-pY-<slug>.md` and keep working
  against the mock.
- **Found a bug in another partition?** File a request with a minimal repro. Do
  not patch their code.
- **Never change `schema/` without a CONTRACT-CHANGE PR.** Approval from all
  three partitions plus a `schema/CHANGELOG.md` entry
  ([CONTRIBUTING.md](CONTRIBUTING.md)).
- **P3 talks to data ONLY through MCP tools.** It imports neither `data/` nor
  `calc/`.
- **P2 talks to storage ONLY through the Protocols** in
  `schema/contracts/interfaces.py`.
- **`calc/` is pure**: no network, no database, no LLM.
- **`audit/` reads a `ResearchState` and a `Factsheet` only**; text and LLM
  access are injected callables.
- **P1 knows nothing about agents.**

**The one sanctioned cross-partition import** in the entire repo:
`mcp_server/tools/calculate_valuation.py` (P1) imports `calc.api` (P2). It is a
pass-through and holds no formula
([ADR 0007](docs/adr/0007-partition-boundaries.md)). Adding a second needs a new
ADR.

---

## 4. Conventions

- **Fractions, not percents.** `0.25` means 25%. Never `25`.
- **Money in full USD.** Not thousands, not millions. `scale` on a
  `FinancialFact` is provenance only — `value` is already normalized.
- **ISO 8601** dates (`YYYY-MM-DD`); UTC ISO 8601 timestamps.
- **Periods**: `FY2025`, `Q2-2026`, from the filer's own fiscal year end.
- **Tickers**: `^[A-Z]{1,5}([.-][A-Z])?$` — also the input allow-list.
- **`snake_case`** keys; lowercase enum values.
- **Missing data is `{"value": null, "status": "unavailable"}`.** Never `0`,
  never `"N/A"`, never an omitted key.
- **Sign conventions**: capex is **positive** meaning cash spent; net debt is
  positive when debt exceeds cash; `FCF = op_cash_flow - capex`.
- **Horizons**: `short_term` (0-12m), `medium_term` (1-3y), `long_term` (3-5y).
- **Additive changes only** without sign-off. A rename or removal is breaking.
- **Consumers tolerate unknown extra fields.** Never fail on extras.

---

## 5. Mock mode

`MODE=mock` and `LLM_MODE=mock` are the defaults. Everything runs offline, with
no keys and no database, against the fictional company **ACME**.

- Only `ACME` (in scope) and `BANKX` (out of scope, exercises the rejection
  path) exist in mock mode.
- `LLM_MODE` is separate from `MODE` on purpose: P1 and P2 can work with no
  Anthropic key at all.
- **Keep mock mode working when you go live.**

> **ACME is FICTIONAL.** Never present mock numbers as real market data.

---

## 6. How to run the tests

```bash
make setup            # once per clone: deps + git hooks
make lint             # ruff
make test-contracts   # the shared contract suite - MUST pass before every commit
make test             # lint + contracts + your partition's tests
make mock-run         # end-to-end mock run
```

Live checks, once you have keys in `.env`:

```bash
make check-live BM_TEST_TICKER=MSFT
```

---

## 7. Before EVERY commit

```bash
git status                          # stage explicit paths only:
git add <your paths>                # NEVER `git add -A` or `git add .`
make lint
make test-contracts
make check-ownership P=p1|p2|p3
git commit -m "[p1] short message"  # prefix [p1] [p2] [p3] [step0]
```

Before merging to `main`: `git fetch && git rebase origin/main`, then re-run
both checks. Never force-push `main`.

**Update `docs/pN/STATUS.md` whenever something moves from mock to real.**

---

## 8. Never commit secrets

Real keys live only in your local, gitignored `.env`. A pre-commit scan
(`make setup` installs it) blocks commits that look like they contain one.

---

## 9. Ground truth

| Question | File |
|---|---|
| What are the contracts? | `schema/contracts/` (models) → `schema/*.json` (generated) |
| What runs when? | [docs/pipeline.md](docs/pipeline.md) |
| What is a fact? | [docs/data-model.md](docs/data-model.md) |
| What does the verifier check? | [docs/verification.md](docs/verification.md) |
| What tools exist? | [docs/mcp-tools.md](docs/mcp-tools.md) |
| What is a `ResearchState`? | [docs/research-state.md](docs/research-state.md) |
| Why is EDGAR data like this? | [docs/sec-pitfalls.md](docs/sec-pitfalls.md) |
| What is next? | [docs/roadmap.md](docs/roadmap.md) |
| Why was this decided? | [docs/adr/](docs/adr/) |

Sample data: `fixtures/mock/` (ACME, generated by
`scripts/gen_mock_fixtures.py`). The pre-restructure planning document is
`archive/plan.txt` — historical context only, superseded by the docs above.
