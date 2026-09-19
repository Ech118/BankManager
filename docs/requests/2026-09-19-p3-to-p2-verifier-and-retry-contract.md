# P3 -> P2: how P3 calls the verifier and executes your retry directives

**From:** P3  **To:** P2 (`audit/`)  **Urgency:** low until `audit/` leaves stub mode, but please confirm before you build against it.

P3 built its side of the verification gate against the contracts and a stub auditor. Four interpretations to confirm:

## 1. `verify_claim(claim, passage) -> bool`

`agents/verifier.py::make_verify_claim()` returns the callable. P3 reads `audit/llm_checks.py`'s signature as
`(claim text, passage text)`. `passage` may be the **full cited section** or just the **quote**; the prompt only asks
whether the passage supports the claim, so either works, but the full section gives the model the context to judge a
paraphrase (`prompts/verifier.md` describes the section as an input).

It **fails closed**: any model error, refusal, malformed output or unexpected verdict returns `False`. It runs on the
cheap tier (`claude-haiku-4-5`), max 300 output tokens, and exposes `verify_claim.stats` (calls, tokens, outcomes) for cost
accounting. In `LLM_MODE=mock` it always returns `False` (it never vouches for a claim offline).

## 2. P3 executes `VerificationResult.retries_issued`

`orchestrator/retry.py` runs the directives you return: it re-runs `directive.target_agent` (the whole agent, one model
call), keeps only the claims for `directive.section_key`, feeds `directive.issues` back into the prompt (issue type,
message, the claim's own text, `expected`, `actual`), then calls `run_audit` again. At most two rounds.

**What P3 needs from `run_audit`:**
- Read the attempt from `section.retry_count` (P3 increments it once per directive it applies), and **stop issuing
  directives once a section reaches `max_attempts`**. P3 also stops after two rounds, but the section-level count is the
  source of truth.
- Issue **one directive per section**, all its issues together (as `routing.build_directives` documents).
- Do not issue directives for `recompute_mismatch` or `future_fact`; P3 will mark those claims `unverified` and continue.

## 3. Claim ids change on retry

Replacement claims are named `claim:<agent>:r<attempt>-<n>-<slug>` so ids stay unique across the state. Do not assume a
claim id is stable across two audits of the same run.

## 4. After the cap

Claims that still carry an `error`-severity issue are set to `verification_status = unverified` (and their section too);
the rest are `verified`. P3 does **not** rewrite your `VerificationResult`, so its counters (`claims_unverified`, ...) are
whatever your final audit reported.

Every retry re-runs the **whole** `run_audit`, including any LLM checks. If that is expensive, consider caching
`verify_claim` results by `(claim, passage)` inside `audit/`.
