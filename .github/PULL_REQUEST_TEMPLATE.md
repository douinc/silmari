<!-- Thanks for contributing to Silmari. Keep PRs focused; see CONTRIBUTING.md. -->

## What & why

<!-- What does this change and why? Link any issue. -->

## Checklist

- [ ] `uv run pytest -q` is green — and stays **offline** (no live database or external LLM)
- [ ] `uv run ruff check .` and `uv run mypy packages/silmari-core/src packages/silmari-runtime/src` are clean
- [ ] Tests added/updated for the new behavior
- [ ] No real or sensitive data, and no domain-specific identifier, introduced — synthetic only

## Safety invariants (must be preserved — see CONTRIBUTING.md)

- [ ] **Read-only**: no new write path to the data source
- [ ] **Scoped**: a bot/rule still reads only its declared tables
- [ ] **Signals, not verdicts**: outputs keep the not-a-verdict note; nothing is auto-applied
- [ ] **Audited**: no path that bypasses the audit log
- [ ] **Local-first**: source data leaves only to a `local/*` model; anything else is redacted first
