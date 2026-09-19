# The pipeline

The canonical order of operations. If this document and the code disagree, this
document is the specification and the code is the bug.

---

## The canonical pipeline

```
Ingest (code: SEC filings, XBRL facts, filing sections, market snapshot, news)
  -> Financial Agent  ||  Business Agent                          [parallel]
  -> Valuation Agent        (picks peers and methods; calls
                             calculate_valuation, never does math)
  -> Scenario Agent         (bear/base/bull, explicit probabilities with
                             rationale, expected value, expected return vs S&P
                             expected return per horizon, sensitivity)
  -> Red Team               (argues the bear case from the RAW facts; may add
                             risks and push the scenario prior down, within cap)
  -> calc.evaluate_scenarios (weights clamped into band, prior shift capped)
  -> Synthesizer            (thesis, red-team responses, catalyst/risk,
                             $10k answer)
  -> Verifier               (deterministic checks, then LLM checks)
       FAIL -> targeted retry of the owning agent, max 2 retries
       PASS or cap reached -> failed claims marked unverified
  -> Report Generator       (templated from ResearchState)
```

---

## Stage by stage

### 1. Ingest — code, not an agent

`data/` produces a `Factsheet` plus `FinancialFact` rows, and `calc/` computes
`Metrics` from it. No LLM has run yet.

`check_scope` runs **first**. An out-of-scope company (bank, insurer, REIT,
pre-revenue) is refused with a reason before a single token is spent. Producing
a confident-looking verdict for a company whose accounting the model does not
describe is worse than refusing.

Missing data becomes `{"value": null, "status": "unavailable"}` plus a
`data_quality` gap. It never becomes `0`, and it never falls through to an agent
guessing.

### 2. Financial and Business agents — in parallel

They are independent and must actually run concurrently: wall-clock is otherwise
the sum rather than the max, and the per-agent UI lanes have nothing to show.

They do not see each other's output. Two independent readings of the same
company exist before anything is reconciled, which is what makes
`cross_agent_contradiction` a meaningful check later.

### 3. Valuation Agent

Reads both. Chooses methods and peers, justifies both, and calls
`calculate_valuation` for every number.

Its most valuable output is the **expectations** section: the reverse DCF says
what growth today's price implies, and the agent judges whether the filings
support it. "What is it worth?" mostly returns the analyst's own assumptions;
"what would have to be true for this price to be right?" is a question evidence
can answer.

### 4. Scenario Agent

Supplies bear/base/bull inputs, a requested weight per case, and a requested
tilt to the prior — each with a written rationale.

It does **not** produce `P(beat S&P)`, a score, or a price target.

### 5. Red Team

Runs after the Scenario Agent and before the audit.

**Gets the raw fact sheet**, not just the other agents' summaries. Given only
their conclusions it restates them in a sceptical tone, which reads like
disagreement and is not.

Produces the strongest case against the leading view, the most plausible
drawdown path, additional risks, and optionally a downward prior shift with a
reason.

### 6. Scenario evaluation — `calc.evaluate_scenarios`

Where LLM proposals become bounded numbers. Runs after the Red Team so both
agents' prior-shift requests are in hand.

#### The weight-bounding algorithm

1. **Reject** weights that do not sum to 1.0. A proposal that is not a
   distribution is an agent bug, not something to silently normalize.
2. **Clamp** each weight into `default ± SCENARIO_WEIGHT_BAND`
   (bear 0.30, base 0.50, bull 0.20, band ±0.15).
3. **Redistribute** the residual across the weights that were *not* clamped, in
   proportion to their size.
4. **Record** one `WeightClamp` per scenario: `requested`, `clamped_to`,
   `applied`, plus `was_clamped` and `was_renormalized`.

Step 3 is the subtle one. Naive renormalization — scaling all three to sum to 1
— pushes a clamped weight straight back outside its band, undoing step 2.
Sending the residual only to the untouched weights keeps every applied weight
inside its own band.

Worked example, from `fixtures/mock/scenario_weights_clamped.json`:

| | requested | clamped_to | applied |
|---|---|---|---|
| bear | 0.55 | **0.45** (band cap) | 0.45 |
| base | 0.30 | 0.30 | 0.3333… |
| bull | 0.15 | 0.15 | 0.1667… |

Clamped, **never rejected**: all three weights survive, the distribution still
sums to 1, and the record shows exactly what the agent wanted.

#### The prior cap

`P(beat S&P)` starts from the historical base rate (~0.47 / 0.44 / 0.42 by
horizon). The Scenario Agent's and the Red Team's requested shifts are **summed**
— so two agents cannot exceed the cap by splitting a request — then capped at
`PRIOR_SHIFT_CAP`. `requested_shift` and `applied_shift` are both recorded.

### 7. Synthesizer

Writes the thesis, answers the Red Team point by point, chooses the primary
catalyst and biggest risk, gives the $10,000 answer, and reconciles
contradictions.

Emits no numbers. Renders no document. Its verdict word must satisfy
`validate_consistency` or the run fails.

### 8. Verifier — `audit.run_audit`

Seven deterministic checks, then one LLM check. See
[verification.md](verification.md).

### 9. Retry

A failed claim lives in one section; each section has one owning agent. The
`RetryDirective` goes to that agent, for that section, with the failures
explained — **max 2 attempts**.

After the cap the report **ships** with the failing claims marked `unverified`.
Blocking would trade a visible flaw for an invisible one.

Two issue types are never retried: `recompute_mismatch` (a `calc/` bug) and
`future_fact` (a `data/` bug). Re-prompting cannot fix either.

### 10. Report Generator

Renders a `Verdict` from the `ResearchState`, deterministically. No LLM. The
same state always produces the same report.

---

## Horizons

| Key | Label |
|---|---|
| `short_term` | 0-12m |
| `medium_term` | 1-3y |
| `long_term` | 3-5y |

The keys match `Scores`, so returns and scores line up in the same table.
`card.p_beat_sp500_5y` is `p_beat_sp500.long_term`.

---

## What runs where

| Stage | Partition | Module |
|---|---|---|
| Ingest | P1 | `data/`, via `mcp_server/` |
| Metrics | P2 | `calc/` |
| Agents | P3 | `agents/` |
| Scenario evaluation | P2 | `calc/scenarios/` |
| Verification | P2 | `audit/` |
| Retry routing | P2 decides, P3 executes | `audit/routing.py`, `orchestrator/retry.py` |
| Report | P3 | `orchestrator/report/` |
