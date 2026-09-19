# web/ — P3

**Owner: P3.** Rules: [docs/p3/CLAUDE.md](../docs/p3/CLAUDE.md).

Next.js UI. Built against `fixtures/mock/verdict.json` from day one, so it is
never blocked on P1 or P2 — and is the most reassignable piece of work in the
project if P3 falls behind.

## Layout rules

These come from the original plan review and are not stylistic preferences.

1. **Verdict card first.** The original design put the verdict after fifteen
   sections, which buried the answer the reader came for.
2. **The case against, immediately after the card.** The red team's summary and
   the synthesizer's response sit above the supporting detail, not below it.
3. **Sections expandable**, collapsed by default.
4. **One lane per agent** during a run, fed by the SSE stream. This is also the
   clearest demo visual: a viewer can see two agents running at once.
5. **Colour-code every number** by `type`: `fact`, `estimate`, `assumption`. A
   discount rate and a reported revenue must not look alike.
6. **`unavailable` renders as "unavailable"**, never as 0 or a blank cell.
7. **Unverified claims render with a visible marker**, never hidden. A reader
   must be able to tell a checked report from an unchecked one.
8. **Data-quality banner** whenever `data_quality.overall` is not `ok`.
9. **The disclaimer appears on every page.** There is a test for it.

## Layout

```
lib/types.ts   TypeScript view of schema/*.json
lib/api.ts     orchestrator client (mock loader, live fetch, SSE)
app/           Next.js routes and components (TODO Step 2)
```

## Why hand-written types today

`schema/*.json` is generated from the pydantic contracts, and exists in
committed form precisely so non-Python consumers like this one have something to
read. `lib/types.ts` mirrors it by hand for now;
[TODO Step 2] generates it instead, so the two cannot drift.

## Running

```bash
npm install
npm run dev     # reads fixtures/mock/verdict.json while MODE=mock
```
