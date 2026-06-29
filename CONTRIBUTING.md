# Contributing to Silmari

Thanks for your interest. Silmari is the **generic engine** — governed, read-only, scoped,
audited data access + a runtime that derives review-priority signals (실마리) from rules. Domain
rule *content* (clinical or otherwise) is intentionally **out of scope** here; keep it in your
own private overlay.

## Project shape

- `packages/silmari-core` — governance library (L1).
- `packages/silmari-runtime` — registry, executor, ruleset engine, sinks, review, API (L2).
- See [`docs/spec.md`](docs/spec.md) for the architecture and data contracts.

## Dev setup

```bash
# Python 3.11+, managed with uv
uv sync --extra dev
uv run pytest -q          # everything runs offline (demo backend, LLM off)
uv run ruff check .
uv run mypy packages
```

The test suite must stay **green and offline** — never require a live database or external LLM.

## Non-negotiable: the safety invariants

Any change must preserve these (there are tests for each — see `docs/spec.md` §6):

1. **Read-only** — no write path to the data source; the SQL guard rejects non-`SELECT`
   (top-level *and* nested), and adapters enforce DB-level read-only.
2. **Scoped** — a bot/rule reads only its declared tables (parse-based, not substring).
3. **Audited** — every access writes an audit row; no bypass path.
4. **Signals, not verdicts** — outputs always carry the not-a-verdict note; no auto-write-back.
5. **PII stays put** — only `local/*` models skip redaction.

PRs that weaken these will not be merged. If you think an invariant is wrong, open an issue to
discuss first.

## Pull requests

- Branch from `main`; keep PRs focused.
- Include tests for new behavior; keep `pytest`/`ruff`/`mypy` green.
- Use clear, imperative commit messages.
- By contributing you agree your work is licensed under the project's Apache-2.0 license.
  *(If a CLA/DCO is adopted, this section will be updated.)*

## Reporting issues

Bugs and feature requests: open a GitHub issue. Security issues: see [`SECURITY.md`](SECURITY.md)
(report privately).
