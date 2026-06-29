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

## Responsible use

- Use a dedicated **read-only** database role/credential.
- Keep sensitive workloads on `local/*` models, or ensure the sensitive-data filter is enabled
  and reachable (fail-closed) for any external model.
- Do not register a remote model under a `local/*` name (it would bypass redaction).
- Outputs are **review-priority signals (실마리), not verdicts** — keep a human in the loop; do
  not auto-write results back to a system of record.

## Reporting a vulnerability

Please report security issues privately to **security@example.com** (replace with the project
contact) rather than opening a public issue. We aim to acknowledge within a few business days.
