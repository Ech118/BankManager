# BankManager

AI equity-research web app (hackathon). Enter a ticker; the app pulls SEC filings
and market data, computes every financial number in code, runs a panel of LLM
analyst agents plus a red team, and produces an investment-committee verdict on
whether the stock is likely to beat the S&P 500 over 1, 3 and 5 years.

> AI-generated research for educational purposes only. Not investment advice.

**Start here:** `plan.txt` (living planner context) and `CLAUDE.md` (rules for
every Claude instance working in this repo).

## Team layout (three partitions, built in parallel)
| Partition | Owns | Produces |
|-----------|------|----------|
| P1 Data & MCP | `data/` `mcp_server/` `fixtures/real/` | fact sheet (`schema/factsheet.json`) |
| P2 Calc, audit & eval | `calc/` `audit/` `backtest/` `predictions/` | metrics, scenario results, audit |
| P3 Agents, orchestrator & web | `agents/` `prompts/` `orchestrator/` `web/` | analyses, verdict, UI |

Partitions talk only through `api.py` files and the JSON schemas in `schema/`.

## Quickstart
```
git clone https://github.com/Ech118/BankManager.git && cd BankManager
cp .env.example .env          # add YOUR OWN keys (never commit .env)
make install-deps
make install-hooks            # pre-commit secret scan
make check-contracts          # should pass on a fresh clone
```
Everything runs in `BM_MODE=mock` by default using the fictional company ACME.

## Repo map
```
plan.txt            planner context; section 15 = partition plan
CLAUDE.md           rules for Claude instances
schema/             FROZEN JSON contracts
fixtures/mock/      FROZEN fictional ACME sample data (+ sections/*.txt filing text)
tests/contracts/    FROZEN contract tests (make check-contracts)
scripts/            check_ownership.sh, secret_scan.sh, gen_mock_fixtures.py
docs/pN/            each partition's notes and STATUS.md
docs/requests/      cross-partition requests (add new files only)
```
