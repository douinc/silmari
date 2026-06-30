# Reference UI — Playwright e2e

A full-stack end-to-end test of the Silmari reference UI (`examples/frontend/index.html`). It boots
`silmari serve --ui --demo-data` (seeded DuckDB + the example bots + the UI, same-origin) and drives
a real browser through: **select a bot → trigger a run → receive the SSE `run_completed` event →
accept a case → see tuning update.**

This is intentionally **isolated from the Python workspace** — it has its own Node tooling and does
**not** run under `uv run pytest` (so the offline Python suite never depends on Node/Chromium).

## Run

```bash
cd examples/frontend/e2e
npm install
npm run install-browsers     # one-time: downloads Chromium
npm test                     # Playwright boots the server (via uv) and runs the e2e
```

Requires Node 18+ and `uv` on PATH (Playwright starts `uv run silmari serve` from the repo root).
