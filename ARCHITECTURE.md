# Architecture

How the pieces fit. Specifications live in [docs/](docs/); this is the map.

---

## 1. Data flow

```
                         ticker + as_of
                               |
                               v
  +--------------------------------------------------------------+
  |  P1  DATA & TRUTH LAYER                          data/        |
  |                                                               |
  |   EDGAR submissions ---+                                      |
  |   XBRL companyconcept -+--> normalize --> FinancialFact rows  |
  |   filing documents ----+     concept map      (provenance,    |
  |   market data ---------+     dimensions        derivation,    |
  |   news ----------------+     YTD -> quarterly  superseded_by) |
  |                              Q4 = FY - 9M                     |
  |                              restatements                     |
  |                                    |                          |
  |                                    v                          |
  |                            Postgres  |  fixtures (mock)       |
  |                                    |                          |
  |                          FactRepository / FilingRepository    |
  |                          / MarketRepository  (Protocols)      |
  +-----------------------------------|---------------------------+
                                      |
                                      v
                            +-------------------+
                            |  mcp_server/  P1  |  10 read-only tools
                            +-------------------+
                             |                 ^
              Factsheet,     |                 | calculate_valuation
              Metrics        v                 |   (the ONE exception)
  +----------------------------+     +---------------------------+
  |  P3  AGENTS & ORCHESTRATOR |     |  P2  CALC  (pure)         |
  |                            |     |                           |
  |  ResearchState + Claims    |<--->|  metrics, valuation,      |
  |                            |     |  scenario bounding,       |
  +----------------------------+     |  prior cap, rubric        |
              |                      +---------------------------+
              |  ResearchState                    ^
              v                                   |
  +----------------------------+                  |
  |  P2  audit/                |------------------+
  |  7 deterministic checks    |   get_text, verify_claim injected
  |  + 1 LLM check             |
  +----------------------------+
              |
              |  VerificationResult (+ RetryDirectives)
              v
  +----------------------------+
  |  P3  report generator      |  deterministic, no LLM
  +----------------------------+
              |
              v
          Verdict --> web/
```

---

## 2. The pipeline

```
  Ingest (code)
     |
     +--> Financial Agent  --+
     |                        |   parallel, independent,
     +--> Business Agent  ----+   neither sees the other
                              |
                              v
                      Valuation Agent        picks peers + methods
                              |              calls calculate_valuation
                              v
                      Scenario Agent         bear/base/bull inputs,
                              |              requested weights + reasons
                              v
                      Red Team               bear case from the RAW facts
                              |              may request a prior shift down
                              v
             calc.evaluate_scenarios         weights CLAMPED into band,
                              |              residual redistributed,
                              |              prior shift CAPPED,
                              |              every clamp RECORDED
                              v
                      Synthesizer            thesis, red-team responses,
                              |              catalyst/risk, $10k answer
                              v
                    audit.run_audit
                              |
              +---------------+---------------+
              |                               |
           PASS                            FAIL
              |                               |
              |                    targeted retry of the
              |                    OWNING agent, max 2
              |                               |
              |                    +----------+----------+
              |                    |                     |
              |                 passes            cap reached:
              |                    |            claims marked
              +--------------------+---------- "unverified"
                              |
                              v
                     Report Generator        templated from ResearchState
                              |
                              v
                          Verdict
```

---

## 3. MCP architecture

```
  P3  orchestrator/mcp_client.py
       |
       |  MODE=mock, tests  -->  in-memory transport (in-process)
       |  MODE=live         -->  stdio (subprocess)
       |
       |    Both are REAL MCP. Mock mode does not shortcut to data.api:
       |    a boundary exercised only in production is untested.
       v
  P1  mcp_server/server.py
       |
       +-- tools/search_filings.py -------+
       +-- tools/get_filing_section.py ---+
       +-- tools/search_filing.py --------+
       +-- tools/get_financial_facts.py --+--> data/api.py   (P1)
       +-- tools/get_market_snapshot.py --+
       +-- tools/get_company_profile.py --+
       +-- tools/get_peer_companies.py ---+
       +-- tools/search_news.py ----------+
       +-- tools/resolve_fact.py ---------+
       |
       +-- tools/calculate_valuation.py -----> calc/api.py   (P2)
                                               ^^^^^^^^^^^
                                   THE ONE CROSS-PARTITION IMPORT.
                                   A pass-through. No formula lives here.

  Every data tool request requires an `as_of`, structurally: they inherit
  DataToolRequest. calculate_valuation is a COMPUTE tool and takes none,
  because the factsheet it works from already carries one.

  All ten tools are READ-ONLY. There is no tool that writes.
```

---

## 4. Partition boundaries

```
  +---------------------------------------------------------------+
  |                      schema/contracts/                        |
  |         pydantic models -- everyone may import this           |
  |    (schema/*.json is GENERATED from it by make gen-schema)    |
  +---------------------------------------------------------------+
        ^                      ^                        ^
        |                      |                        |
  +-----------+         +-------------+          +--------------+
  |    P1     |         |     P2      |          |      P3      |
  |           |         |             |          |              |
  | data/     |         | calc/       |          | agents/      |
  | mcp_server|-------->| audit/      |          | prompts/     |
  | fixtures/ | the ONE | backtest/   |          | orchestrator/|
  |   real/   | import  | predictions/|          | web/         |
  +-----------+         +-------------+          +--------------+
        ^                                               |
        |                                               |
        +-------------- MCP tools only -----------------+
                    (P3 never imports P1 or P2)

  calc/   is PURE: no network, no DB, no LLM
  audit/  reads a ResearchState + Factsheet only; get_text and
          verify_claim are INJECTED, so it imports neither data/
          nor any model SDK
  P1      knows nothing about agents
```

### Who owns what

| Directory | Owner | Deliverable |
|---|---|---|
| `data/` `mcp_server/` `fixtures/real/` | **P1** | the fact sheet |
| `calc/` `audit/` `backtest/` `predictions/` | **P2** | metrics, scenario results, audit |
| `agents/` `prompts/` `orchestrator/` `web/` `tests/e2e/` | **P3** | analyses, verdict, UI |
| `schema/` `fixtures/mock/` `tests/contracts/` `scripts/` | **shared** | changed only by CONTRACT-CHANGE PR |

---

## 5. Where the LLM is bounded

Three places, all in code no prompt can reach. They are the difference between
research and confident-sounding generation.

```
  Scenario Agent proposes                calc/ decides
  -----------------------                -------------
  weights (bear/base/bull)    ------>    clamped into default +/- band,
                                         residual redistributed across
                                         the UNCLAMPED weights,
                                         every clamp RECORDED

  prior_shift (+ Red Team's)  ------>    SUMMED, then capped at
                                         PRIOR_SHIFT_CAP; requested and
                                         applied both recorded

  (nothing)                   ------>    score, from a fixed rubric table
```

And every number an agent states must cite a `fact_id` or appear in a quote it
supplied — enforced by the `Claim` model, not by a prompt.

---

## 6. Modes

| | `MODE=mock` | `MODE=live` |
|---|---|---|
| data | `fixtures/mock/` via fixture repositories | Postgres + EDGAR/market/news |
| database | none required | `DATABASE_URL` |
| MCP transport | in-memory | stdio |
| API keys | none required | `SEC_USER_AGENT`, market/news keys |

`LLM_MODE` is independent: `mock` returns canned agent outputs, so P1 and P2
need no Anthropic key.

A fresh clone runs the whole pipeline offline. That is what lets three people
build in parallel without waiting on each other.
