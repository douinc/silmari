---
name: Feature request
about: Propose an addition to the engine
title: "[feat] "
labels: enhancement
---

**Problem**
What are you trying to do that Silmari doesn't support today?

**Proposal**
What you'd like to see. Keep in mind Silmari is the **generic engine** — domain
rule *content* and domain-specific scoring/recommendation logic are intentionally
out of scope (see [`CONTRIBUTING.md`](../../CONTRIBUTING.md)). Does this work for
any read-only data source, or is it domain-specific?

**Safety**
Does it touch any of the invariants (read-only, scoped, signals-not-verdicts,
audited, local-first)? How does it preserve them?

**Alternatives**
Anything you've considered or worked around.
