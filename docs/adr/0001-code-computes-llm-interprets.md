# ADR 0001 — Code computes, the LLM interprets

**Status:** accepted (Step 0) · **Supersedes:** the single-prompt design in
`archive/plan.txt` §3

## Context

The project began as one prompt asking a model to produce fifteen sections of
equity research, including "use current market data" and "calculate the implied
growth rate".

Three things go wrong with that, reliably:

1. **Language models are unreliable at arithmetic**, and unreliable in the worst
   way: the answer is well-formatted, confident, and close enough to be
   plausible. A margin off by two points survives review.
2. **A model has no live data**, and its training data is stale by construction.
   Asked for a current price it produces one anyway.
3. **Numbers produced by generation are not reproducible.** The same prompt on
   the same filing yields different figures, so nothing downstream can be
   checked against anything.

## Decision

**No agent ever produces a number by doing arithmetic.** All metrics and
valuation math are deterministic code in `calc/`.

- `calc/` is pure: no network, no database, no LLM.
- Agents obtain numbers by citing a `fact_id`, or by calling
  `calculate_valuation`.
- Agents choose *methods* and interpret *results* — which is judgement, and what
  they are actually good at.
- The constants that drive the math live in `calc/config.py`, tagged
  `assumption`, where no prompt can reach them.

The division is not "hard math in code, easy math in the prompt". It is **all**
arithmetic in code, including divisions that look trivial, because the failure
mode is a number that looks right.

## Consequences

**Good**

- Every number is reproducible, and therefore checkable. `audit/`'s
  `recompute_mismatch` check exists only because `calc/` is pure.
- Agents get a better task: judging whether an implied growth rate is plausible
  is a language problem, not a numerical one.
- A wrong number is a bug with a stack trace, not a bad sample.

**Costs**

- More code. Every metric has to be implemented rather than described.
- The valuation agent cannot improvise a method that `calc/` does not implement.
- One tool must cross the partition boundary (`calculate_valuation`), since MCP
  is the only surface agents can reach. See
  [ADR 0007](0007-partition-boundaries.md).

## Addresses

Flaws **3** (LLM does arithmetic), **8** (expectations-vs-reality was only
prose), and **C** (unanchored probabilities) from `archive/plan.txt`.
