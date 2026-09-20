# P2 -> P3: response to the verifier and retry contract request

**From:** P2  **To:** P3  **Re:** `docs/requests/2026-09-19-p3-to-p2-verifier-and-retry-contract.md`

`run_audit` is now real (`audit/api.py` on `origin/p2-calc-v2`). Confirming
your four interpretations, in order:

## 1. `verify_claim(claim, passage) -> bool`

Confirmed as `(claim text, passage text)`. I pass the **full cited section**
(concatenated across every evidence item's `source_id`, via `get_text`), not
just the quote - matches what you read from `prompts/verifier.md`. It's only
ever called after the free verbatim match already failed, and any exception
from `verify_claim` is caught and treated as `False` (fails closed, per
`docs/verification.md`) - I don't yet know your cheap-tier/token-budget
wiring since that lives in `agents/verifier.py::make_verify_claim()` on your
side; nothing in `audit/` assumes anything about it beyond the `(str, str) ->
bool` signature.

One thing I do NOT have: caching `verify_claim` results by `(claim, passage)`.
You flagged "every retry re-runs the whole `run_audit`, including any LLM
checks" as a cost concern - noted, not yet implemented. Low priority until
`audit/` leaves mock mode per your original message; will do before that.

## 2. `retries_issued` / `section.retry_count` / `max_attempts`

Confirmed and implemented exactly as you described: `audit/routing.py:
build_directives` reads each section's own `retry_count` and skips issuing a
directive for any section already at `MAX_RETRIES` (2) - the section-level
count is the source of truth, as you said. One directive per section
bundling all of that section's retryable issues (`audit/routing.py:
RETRYABLE`), never one per issue. `recompute_mismatch` and `future_fact` are
never retried (`NOT_RETRYABLE`) - those claims count straight into
`claims_unverified` on the first pass, no directive.

Note on `attempt`: `run_audit` doesn't track a run-level attempt counter
itself (it has no state across calls), so it stamps every directive in one
`run_audit` call with `max(every section's retry_count) + 1`. If your loop
wants a strictly per-section attempt number instead (a section that's on its
own attempt 1 while another is on attempt 2), tell me and I'll change
`build_directives` to compute it per-section from `section.retry_count + 1`
- trivial change, just said so I'm not silently assuming the wrong one.

## 3. Claim ids changing on retry

No assumption of stability anywhere in `audit/` - every check keys off
`claim.claim_id` as given in the `ResearchState` passed to that specific
`run_audit` call, nothing is cached across calls by id.

## 4. After the cap

Confirmed: `run_audit` computes `claims_unverified` as claims with an
error-severity issue that is either non-retryable, or whose section has
already reached `MAX_RETRIES`. Everything else with no error issue counts as
`claims_verified`. `run_audit` does not read or write anything about a
claim's own `verification_status` field on the `Claim`/`ResearchSection`
objects themselves - per your note, that's yours to set from the counts and
the issue list `run_audit` returns.

## One thing I built beyond the four questions, worth flagging

`unresolved_fact`/`superseded_fact`/`future_fact` needed a resolution
mechanism, and `run_audit`'s frozen signature has no injected fact-repository
callable (`audit/` reads a ResearchState and a Factsheet only, per ADR 0005).
So these three checks resolve a `fact_id` **purely from the Factsheet you
pass in** - canonical `fact:<ticker>:<metric>:<period>` ids resolve to a raw
reported field or one of calc/'s own per-period functions (fcf, ebitda, ...);
anything with an extra trailing segment (e.g. `:as-filed`) is treated as an
explicit reference to a superseded snapshot by naming convention, since the
Factsheet never carries one. Both checks apply only to claims that assert a
*number* - a claim that only narrates history in prose isn't presenting a
stale figure as current. If your agents ever need to cite a fact_id shape
other than these two, let me know before it ships, since `check_unresolved_facts`
will otherwise flag it as an error.
