# Silmari (실마리)

**Define rules over a read-only data source; Silmari safely derives _실마리_ — review-priority
leads (signals) — for a human to decide.**

*실마리* = a clue / the loose thread you pull to unravel something. That is exactly what Silmari
surfaces: the leads worth a human's attention — never a verdict.

Most "text-to-SQL" / DB-agent tools let a model **write** to your database, send your data to the
model, and keep no audit trail. Silmari is **safe by default**:

- **Read-only** — SQL is parsed and rejected unless it is a pure `SELECT`; point it at a
  read-only DB role for a hard, database-enforced guarantee.
- **Scoped** — a bot/rule may only read the tables it declares.
- **Audited** — every access writes a metadata-only audit row.
- **PII-filtered** — only `local/*` models are exempt; any other model call is redacted first.
- **Human-in-the-loop** — outputs are review-priority *signals* (실마리), never auto-applied.

## Two layers

- **`silmari-core`** — the governance library: safe, read-only, scoped, audited, redacted data
  access for LLM agents. Drop it into any stack.
- **`silmari-runtime`** — batteries-included framework: rule/bot registry, scheduler, agent
  authoring, sinks, and the human review loop.

## The core loop

```
정의(rule/bot) → Silmari가 read-only·scoped·audited로 실행 → 실마리(검토 신호) 도출 → 사람이 검토·결정
```

You bring the **rules** (a declarative ruleset, or a Python bot). Silmari brings the **safe
execution + derivation + review**.

## Status

New project — extracted as the generic engine from an on-premise clinical/coding intelligence
platform. Implementation spec: [`docs/spec.md`](docs/spec.md).

## License

Apache-2.0 (planned).
