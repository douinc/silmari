---
name: Bug report
about: Something doesn't behave as documented
title: "[bug] "
labels: bug
---

**What happened**
A clear description of the bug.

**Expected**
What you expected instead.

**Reproduce**
Minimal steps. If it involves a bot/ruleset, include a minimal `manifest.yaml` +
`pipeline.py`/`ruleset.json` and the command you ran (e.g. `silmari run …`,
`silmari serve …`). Use synthetic data only — never paste real or sensitive data.

**Environment**
- silmari-core / silmari-runtime version (or commit):
- Python version (`python --version`):
- Data source adapter (DuckDB / SQLite / Postgres / other):
- OS:

**Logs / output**
Relevant output (`uv run pytest -q`, tracebacks, etc.). Redact anything sensitive.

> Security vulnerabilities: do **not** open a public issue — see [`SECURITY.md`](../../SECURITY.md).
