# web/ — P3

You are working in **P3**. Full rules: [docs/p3/CLAUDE.md](../docs/p3/CLAUDE.md).

Builds against `fixtures/mock/verdict.json`, so it is never blocked on a
backend.

Non-negotiable in the UI:

- the disclaimer on every page (there is a test)
- `unavailable` renders as "unavailable", never as 0 or a blank
- unverified claims render **with a marker**, never hidden
- numbers colour-coded by `type`: fact / estimate / assumption
- verdict card first, the case against immediately after it

`web/` is the most reassignable piece of work in the project. Keep it
mock-driven so it stays that way.
