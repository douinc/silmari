# Silmari — Implementation Plan

*Status: draft v0 · Companion to [`spec.md`](spec.md) (architecture & contracts). This doc is the
**build order**: phases, concrete modules, what to port from the source platform, tests, and a
definition of done (DoD) per phase.*

## How to use this

- Build **top to bottom**. Each phase depends on the ones above it.
- silmari is the generic engine **extracted from an existing on-prem platform ("subal")**, so most
  modules are a *port + harden + genericize*, not a from-scratch build. The "Port from subal"
  column says what to reuse.
- **New vs port:** the safety hardening (sqlglot guard, DB-level read-only adapters, configurable
  masking, generic entity model) is **new** — subal does not have it. Everything else is mostly a
  port.
- Every phase ends **green and offline** (`uv run pytest -q`, no live DB/LLM).
- Size: S ≈ ≤1 day · M ≈ 2–4 days · L ≈ ~1 week (rough, single dev).

## Dependency graph

```
P0 scaffold
  └─ P1 silmari-core (safety primitives)   ← the foundation; build well
       ├─ P2 runtime base (manifest · registry · executor · Signal · store)
       │    ├─ P3 ruleset engine (rules → signals)
       │    ├─ P4 delivery + review (sinks/SSE · API · review loop)
       │    └─ P5 authoring (local agent · CLI)
       └─ (P1 ships standalone via pip first)
P6 polish → public release
```

---

## P0 — Repo scaffolding  ·  size S

**Goal:** a working uv workspace with two packages, tooling, and CI.

- `pyproject.toml` (workspace) + `packages/silmari-core/` + `packages/silmari-runtime/` skeletons.
- Tooling: `ruff`, `mypy`, `pytest` (+ `pytest-asyncio`), pinned `.python-version` (3.12).
- `.github/workflows/ci.yml`: `uv sync` → ruff → mypy → pytest, on push/PR.
- `silmari_core/__init__.py`, `silmari_runtime/__init__.py` with `__version__`.

**DoD:** `uv sync --extra dev` works; empty `pytest` green; ruff/mypy clean; CI green.

---

## P1 — `silmari-core`: safety primitives  ·  size L  (M0+M1)

The gem. This is where "safe DB access" becomes **true in code** (subal's guards are bypassable;
the real read-only lived only in its private Vertica adapter — we fix that here).

| Module | What | Port from subal | New? |
|---|---|---|---|
| `silmari_core/sql.py` | `assert_read_only(sql)`, `tables_referenced(sql)` via **sqlglot** | — | **NEW** |
| `silmari_core/source.py` | `DataSource`(ABC: `query/sample/stats/schema` + `_execute/_schema`), `ScopedSource`, `DataAccess`, `connect()` | `cdw/interface.py` (structure) | port + **harden** |
| `silmari_core/audit.py` | `AuditLog`, `AuditRow` (SQLAlchemy/SQLite, metadata-only) | `cdw/audit.py` | port ~as-is |
| `silmari_core/adapters/{sqlite,duckdb,postgres}.py` | adapters with **DB-level read-only** | `cdw/mock_data.py` (mock only) | **NEW** (real read-only) |
| `silmari_core/masking.py` | configurable identifier-masking policy | `_DIRECT_IDENTIFIERS` (idea) | **NEW** (config-driven) |
| `silmari_core/sensitive.py` | redaction interface; depends on **phi-hook** | `privacy/` shim | port |
| `silmari_core/llm.py` | `LLMClient` (LiteLLM via httpx), `is_local_model`, redaction gate, `summarize` | `llm/client.py` | port + genericize |
| `silmari_core/config.py` | pydantic-settings (`DATA_BACKEND`, `LLM_*`, `*_FILTER_*`) | `config.py` | port + rename |

**Build order inside P1:** `sql.py` → `audit.py` → `source.py`/`ScopedSource` → adapters →
`masking.py` → `sensitive.py` + `llm.py` → `config.py`.

**Tests (the safety acceptance suite — backbone of the project):**
- INSERT/UPDATE/DELETE/DDL rejected, top-level **and** nested in subquery/CTE.
- A `SELECT` mentioning a non-allowed table only in a comment/string is **not** scoped-in.
- Each adapter physically rejects a write at the DB layer (round-trip test).
- Every `query`/`schema` call writes exactly one audit row; no bypass.
- Masking is config-driven (no hardcoded columns).
- `is_local_model` gates redaction; non-local path is redacted.

**Deliverable:** `silmari demo` (DuckDB + tiny synthetic data): DROP blocked / unauthorized table
blocked / PII redacted / all audited. This demo doubles as the README centerpiece.

**DoD:** `silmari-core` installs standalone via pip; safety suite green offline; demo runs.

---

## P2 — `silmari-runtime`: base  ·  size L  (M2)

| Module | What | Port from subal |
|---|---|---|
| `silmari_runtime/manifest.py` | pydantic `BotManifest` (`data_access`, `trigger`, `kind`, `sinks`, `audit`) | `registry/manifest.py` (rename `cdw_access`→`data_access`) |
| `silmari_runtime/registry.py` | git-backed loader (`importlib`, `sys.modules` pre-reg) | `registry/loader.py` |
| `silmari_runtime/signal.py` | `Signal` (실마리 record), `signal()`/`result()`, `confidence_band`, not-a-verdict default; **generic `subject` = entity_id + attrs** | `prediction/pipeline.py` (genericize subject) |
| `silmari_runtime/context.py` | `Context`/`BotResult` dataclasses | `executor/context.py` |
| `silmari_runtime/executor.py` | `_begin_run` (begin/execute split), `run_bot`, `start_run` (daemon thread) | `executor/runner.py` |
| `silmari_runtime/store.py` | `ResultStore` (SQLAlchemy/SQLite, lifecycle status) | `executor/result_store.py` |
| `silmari_runtime/scheduler.py` | APScheduler `CronTrigger.from_crontab` | `executor/scheduler.py` |
| `examples/bots/example-signal/` | one pipeline bot on the demo schema | `scaffold` templates |

**Tests:** example bot runs end-to-end offline → emits `Signal`s (with note + entity subject) →
persisted; begin/execute split works (sync + daemon-thread paths).

**DoD:** `silmari run example-signal` produces stored signals offline; tested.

---

## P3 — Ruleset engine (rules → signals)  ·  size M  (M3)

The "define rules → derive 실마리" no-code path.

| Module | What | Port from subal |
|---|---|---|
| `silmari_runtime/ruleset.py` | ruleset schema + evaluator (AND conditions; ops `in/lt/gt/eq/relative_decrease/text_present`), **unsupported-condition reporting**, hot-reload per run | `registry/ruleset.py` + `coding-rule-*/pipeline.py` engine (genericize: no domain codes) |
| `silmari_runtime/proposals.py` | propose → `validate_ruleset` → approve/merge flow | `review/ruleset_proposals.py` + `registry/ruleset.py` |
| `examples/bots/example-ruleset/` | a declarative bot on demo schema | — |

**Tests:** rules → signals; validation (hard errors vs warnings); unsupported conditions reported,
never silently emitted/skipped; hot-reload picks up edited `ruleset.json`.

**DoD:** a `ruleset.json` (no Python) yields signals offline; proposal/validate/approve tested.

---

## P4 — Delivery + review  ·  size M  (M4)

| Module | What | Port from subal |
|---|---|---|
| `silmari_runtime/sinks.py` | in-process event bus (bounded queue, drop-on-full) + webhook + SSE fan-out | `sinks/dispatcher.py` |
| `silmari_runtime/api/` | FastAPI app + routers (`bots`, `runs`+SSE, `review`, `subscriptions`, `admin`) | `api/` |
| `silmari_runtime/review/` | `ReviewStore` (accept/reject/note), threshold `tuning` | `review/{store,tuning,approvals}.py` |

**Tests:** `/v1/bots/{id}/results` returns signals; `/v1/runs/stream` SSE emits lifecycle events;
review decision persists; tuning returns precision/recall + F1-best.

**DoD:** API serves + streams; review loop + tuning work offline; tested.

---

## P5 — Authoring + CLI  ·  size M  (M5)

| Module | What | Port from subal |
|---|---|---|
| `silmari_runtime/agent/` | local-only tool-use loop (`local/*` guard), CDW/authoring tools, `register_bot` (validate vs demo source), conversation store | `agent/{harness,tools,register,bot_ops,authoring,conversation}.py` |
| `silmari_runtime/cli.py` | `silmari demo / new-bot / run / serve` | `scaffold/new_bot.py` + entry points |

**Tests:** scripted local model explores demo source → writes a pipeline → `register_bot` validates
(read-only/scope/not-a-verdict enforced) — fully offline (no live LLM).

**DoD:** conversational bot authoring works offline (scripted); CLI commands work.

---

## P6 — Polish → public release  ·  size M  (M6)

- (Optional) `frontend/` reference review/authoring UI.
- Docs site (architecture, manifest schema, safety model, quickstart), example gallery.
- Final naming pass; confirm `SECURITY.md`/`CONTRIBUTING.md`/LICENSE owner line.
- **Public-readiness review** (the carve-out checklist) → flip repo to public.

**DoD:** public-ready: hardened safety suite green, demo + docs polished, no domain leakage.

---

## Recommended first PRs

1. **PR1 (P0):** scaffold workspace + CI. *(unblocks everything)*
2. **PR2 (P1a):** `sql.py` (sqlglot guard + table extraction) + its tests. *(the highest-value, riskiest correctness piece; nail it first)*
3. **PR3 (P1b):** `DataSource`/`ScopedSource` + `audit.py` + SQLite/DuckDB adapters (DB-level read-only) + safety suite + `silmari demo`.
4. **PR4 (P1c):** `sensitive.py` + `llm.py` + `config.py`. → cut `silmari-core` v0.1.

Then P2 onward.

## Cross-cutting

- **Testing:** the P1 safety acceptance suite is the project's backbone — never let it go red.
- **Offline-first:** mock/demo backend + LLM off are the defaults; CI must not need network.
- **Genericize as you port:** strip every domain term (`CDW`→`DataSource`, `cdw_access`→`data_access`,
  clinical `subject`→generic entity, hardcoded Korean note→config). See the rename table in the
  subal carve-out plan (`douinc/subal:docs/oss/extraction-plan.md`).
- **Dependencies to add:** `sqlglot` (guard), `duckdb`/`psycopg` (adapters), plus the existing
  FastAPI/APScheduler/pydantic/SQLAlchemy/httpx/LiteLLM stack.
