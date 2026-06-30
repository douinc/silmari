# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-30

Initial public release — the generic engine extracted from an on-premise
data-intelligence platform.

### Added

- **`silmari-core`** — governed, read-only, scoped, audited, redacted data access
  for LLM agents: a sqlglot read-only SQL guard, parse-based table scoping, an
  append-only metadata-only audit log, a configurable masking policy, and a
  local-first LLM gate that redacts every non-`local/*` model call.
- **DB-level read-only adapters** — DuckDB, SQLite, and Postgres (the `postgres`
  extra); `connect()` dispatches by URL.
- **`silmari-runtime`** — bot manifest + git-backed registry, executor + APScheduler,
  the Signal (실마리) model with `signal()`/`result()` and a `prediction()` builder
  for `kind: prediction`, a SQLite-backed result store, and a declarative ruleset
  engine (`eq/ne/lt/lte/gt/gte/in/text_present/relative_decrease`, AND/OR).
- **Delivery & review** — an in-process event bus, webhook and SSE sinks,
  subscriptions, a human review loop, and threshold tuning (precision/recall/F1).
- **HTTP API** (FastAPI) — bots, runs + SSE, review, subscriptions, admin, a
  read-only data browser (`/v1/data`), and a gated propose-only authoring endpoint
  (`/v1/authoring`).
- **Local-only authoring agent** — a tool-use loop that explores the read-only
  source and proposes a validated bot (propose-only); `ScriptedLLM` drives it
  deterministically/offline for demos and tests.
- **CLI** — `silmari demo`, `new-bot`, `run`, and `serve` (with `--ui` and
  `--demo-data`).
- **Reference UI** — a single-file example console with a persistent agent dock,
  plus a Playwright end-to-end harness.

### Security

- Licensed under **AGPL-3.0-or-later**; the §13 Corresponding-Source offer is
  surfaced in the API metadata and the reference UI. See [`SECURITY.md`](SECURITY.md)
  for the threat model (the HTTP API is unauthenticated; the authoring agent runs
  proposed code — keep it behind auth and a read-only DB role).

[0.1.0]: https://github.com/douinc/silmari/releases/tag/v0.1.0
