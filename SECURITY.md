# Security & Responsible Use

Silmari gives LLM agents access to databases. That is useful and dual-use, so please read the
honest safety model below before relying on it.

## What Silmari guarantees (and what it doesn't)

Silmari is **defense-in-depth, not a sandbox.** It layers, strongest first:

1. **DB-level read-only** — when you connect via a read-only DB role (or a backend opened
   read-only: Postgres `SET TRANSACTION READ ONLY`, DuckDB `read_only=True`, SQLite
   `PRAGMA query_only`). This is the only layer the database physically enforces.
2. **SQL-parser statement guard** — rejects any statement that is not a pure `SELECT`
   (including nested DML and CTEs), via `sqlglot`.
3. **Table scoping** — an agent/bot may only query the tables it declares (resolved from the
   SQL parse, not substring matching).
4. **Audit log** — every query and schema call is recorded (metadata only).
5. **Sensitive-data redaction** — content bound for non-`local/*` models is redacted first.

**It does NOT guarantee:** protection if you point it at a read-write DB role and disable the
guards; perfect PII detection (redaction is best-effort + a regex floor); protection against a
malicious *operator* who edits the policy. **Always provision a least-privilege, read-only
database role** — no application-layer guard beats a database that physically cannot write.

## The HTTP API is unauthenticated

The optional runtime API (`silmari_runtime.api`) ships with **no authentication** and no CORS by
default. It exposes read access to run results (review-priority signals) and state-changing
endpoints (`POST /run`, review decisions, subscription register/delete, registry reload). Treat it
as a trusted-network service:

- Bind to loopback or a private interface, and put it behind a reverse proxy that enforces auth
  (API key / mTLS / SSO) before exposing it.
- Enable CORS only via `create_app(cors_origins=[...])` with an explicit allow-list — never `*`.
- **Webhook subscriptions are privileged.** A subscription URL is fetched server-side on every run
  completion (an SSRF surface) and receives the full run payload. Silmari restricts the scheme to
  `http(s)` and only interpolates `${WEBHOOK_*}` env vars (so other server secrets cannot be
  exfiltrated via `${...}`), but it does not enforce a destination allow-list — restrict outbound
  egress at the network layer and gate subscription registration behind auth.

## The authoring agent executes proposed pipeline code

To validate an agent-proposed bot, `register_bot` (`silmari_runtime.agent.register`) **imports and
runs the proposed `pipeline.py` in-process** (scoped read-only source, with a wall-clock timeout).
That code is **not sandboxed** — the static "no mutating SQL" check is a cheap pre-filter, not a
boundary; the real data-access guard is the read-only, scoped source. Treat authoring as a
privileged operation:

- Run the authoring agent only with a **`local/*`** model (enforced) and on data you would let that
  code touch; the read-only source bounds *data* access, not arbitrary code execution.
- Review proposed bots before committing/activating them (authoring is propose-only — it writes
  `bots/<id>/` for human review and does not activate).
- For untrusted input, run authoring/validation in an isolated environment (container/VM).
- Over HTTP, authoring is **gated**: the `/v1/authoring` endpoint is inert unless the app is built
  with `create_app(authoring_llm=...)`. `silmari serve --demo-data` wires a deterministic
  `ScriptedLLM`, so the demo only ever runs the fixed pipeline it scripts. Exposing authoring with a
  **real** model means a network caller's prompt drives model-written code that the validator
  executes — only do that behind authentication and in an isolated environment.

## Responsible use

- Use a dedicated **read-only** database role/credential.
- Keep sensitive workloads on `local/*` models, or ensure the sensitive-data filter is enabled
  and reachable (fail-closed) for any external model.
- Do not register a remote model under a `local/*` name (it would bypass redaction).
- Outputs are **review-priority signals (실마리), not verdicts** — keep a human in the loop; do
  not auto-write results back to a system of record.

## Reporting a vulnerability

Please report security issues **privately** via GitHub's private vulnerability reporting — the
repository's **Security** tab → **Report a vulnerability** — rather than opening a public issue.
We aim to acknowledge within a few business days.
