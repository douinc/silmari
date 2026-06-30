"""Declarative ruleset engine: a ``ruleset.json`` (no Python) → review-priority Signals.

A ruleset is a list of rules; each rule has AND/OR-combined criteria over record fields, and an
``output`` block. A matched record becomes a Signal. Everything is domain-neutral: fields and
operators are generic, with no built-in domain vocabulary.

Validation separates **hard errors** (unknown operator, non-numeric value for a numeric operator,
duplicate rule_id, …) from **warnings** (rules that can never fire — empty criteria, or criteria
referencing fields absent from the data). Unsupported rules are always *reported*, never silently
skipped or emitted. The ruleset is re-read from disk on every run (hot-reload).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .context import BotResult
from .signal import Signal, result, signal

if TYPE_CHECKING:
    from .context import Context

SUPPORTED_OPERATORS = (
    "eq",
    "ne",
    "lt",
    "lte",
    "gt",
    "gte",
    "in",
    "text_present",
    "relative_decrease",
)
_NUMERIC_OPERATORS = ("lt", "lte", "gt", "gte", "relative_decrease")

_MISSING = object()


class RulesetError(ValueError):
    """Raised when a ruleset is invalid or cannot be sourced."""


# --------------------------------------------------------------------------- schema


class Criterion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    field: str
    operator: str
    value: Any = None
    baseline_field: str | None = None  # required by relative_decrease

    @field_validator("operator")
    @classmethod
    def _known_operator(cls, v: str) -> str:
        if v not in SUPPORTED_OPERATORS:
            raise ValueError(f"unsupported operator {v!r}; supported: {list(SUPPORTED_OPERATORS)}")
        return v


class RuleConditions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    criteria: list[Criterion] = Field(default_factory=list)
    combination: Literal["and", "or"] = "and"

    def is_empty(self) -> bool:
        return not self.criteria


class Rule(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rule_id: int
    score: float = 0.7
    label: str = "rule_match"
    conditions: RuleConditions = Field(default_factory=RuleConditions)
    output: dict[str, Any] = Field(default_factory=dict)

    @field_validator("score")
    @classmethod
    def _score_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("score must be in [0.0, 1.0]")
        return v


class RulesetDoc(BaseModel):
    model_config = ConfigDict(extra="allow")  # descriptive metadata round-trips

    rules: list[Rule]
    id_field: str = "id"  # which record column is the entity id (Signal.target_id)
    source_table: str | None = None
    query: str | None = None


# --------------------------------------------------------------------------- validation


@dataclass
class RuleWarning:
    rule_id: int
    reason: str


@dataclass
class ValidationReport:
    valid: bool
    rule_count: int
    errors: list[dict[str, Any]] = field(default_factory=list)
    unsupported: list[RuleWarning] = field(default_factory=list)
    doc: RulesetDoc | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "rule_count": self.rule_count,
            "errors": self.errors,
            "unsupported": [{"rule_id": w.rule_id, "reason": w.reason} for w in self.unsupported],
        }


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _unsupported_reason(
    rule: Rule, known_fields: set[str] | None, *, id_field: str | None = None
) -> str | None:
    """Why a rule can never fire (so it is reported AND skipped). None means it can fire.

    Combination-aware: under AND any unevaluable criterion means the rule never fires; under OR the
    rule can still fire as long as one criterion is evaluable.
    """
    if rule.conditions.is_empty():
        return "rule has no criteria; it would match nothing and never emit"
    if known_fields is None:
        return None
    if id_field is not None and id_field not in known_fields:
        return f"entity id field {id_field!r} is not in the data"

    missing_per_criterion = []
    for c in rule.conditions.criteria:
        refs = {c.field} | ({c.baseline_field} if c.baseline_field else set())
        missing_per_criterion.append(sorted(refs - known_fields))
    missing_all = sorted({f for miss in missing_per_criterion for f in miss})

    if rule.conditions.combination == "and" and any(missing_per_criterion):
        return f"references fields not in the data: {missing_all}"
    if rule.conditions.combination == "or" and all(missing_per_criterion):
        return f"references fields not in the data: {missing_all}"
    return None


def validate_ruleset(
    data: dict[str, Any], *, known_fields: set[str] | None = None
) -> ValidationReport:
    try:
        doc = RulesetDoc.model_validate(data)
    except ValidationError as exc:
        parse_errors = [{"loc": [str(p) for p in e["loc"]], "msg": e["msg"]} for e in exc.errors()]
        return ValidationReport(valid=False, rule_count=0, errors=parse_errors)

    errors: list[dict[str, Any]] = []
    seen: set[int] = set()
    for i, rule in enumerate(doc.rules):
        if rule.rule_id in seen:
            errors.append(
                {"loc": ["rules", str(i), "rule_id"], "msg": f"duplicate rule_id {rule.rule_id}"}
            )
        seen.add(rule.rule_id)
        for j, c in enumerate(rule.conditions.criteria):
            loc = ["rules", str(i), "conditions", "criteria", str(j), "value"]
            if c.operator in _NUMERIC_OPERATORS and not _is_number(c.value):
                errors.append(
                    {"loc": loc, "msg": f"operator {c.operator!r} requires a numeric value"}
                )
            if c.operator == "relative_decrease" and not c.baseline_field:
                errors.append({"loc": loc, "msg": "relative_decrease requires 'baseline_field'"})
            if c.operator == "in" and not isinstance(c.value, list | tuple):
                errors.append({"loc": loc, "msg": "operator 'in' requires a list value"})
            if c.operator == "text_present" and not (isinstance(c.value, str) and c.value):
                errors.append(
                    {"loc": loc, "msg": "operator 'text_present' requires a non-empty string value"}
                )
    if errors:
        return ValidationReport(valid=False, rule_count=len(doc.rules), errors=errors)

    unsupported = [
        RuleWarning(rule_id=r.rule_id, reason=reason)
        for r in doc.rules
        if (reason := _unsupported_reason(r, known_fields, id_field=doc.id_field))
    ]
    return ValidationReport(
        valid=True, rule_count=len(doc.rules), unsupported=unsupported, doc=doc
    )


# --------------------------------------------------------------------------- evaluation


def _passes(c: Criterion, row: dict[str, Any]) -> bool:
    if c.operator == "relative_decrease":
        if c.baseline_field is None:
            return False
        try:
            current = float(row.get(c.field, _MISSING))
            baseline = float(row.get(c.baseline_field, _MISSING))
        except (TypeError, ValueError):
            return False
        if baseline == 0:
            return False
        return (baseline - current) / baseline * 100.0 >= float(c.value)

    val = row.get(c.field, _MISSING)
    if val is _MISSING:
        return False
    if c.operator == "eq":
        return bool(val == c.value)
    if c.operator == "ne":
        return bool(val != c.value)
    if c.operator == "in":
        return isinstance(c.value, list | tuple) and val in c.value
    if c.operator == "text_present":
        return str(c.value).lower() in str(val).lower()
    try:
        v, threshold = float(val), float(c.value)
    except (TypeError, ValueError):
        return False
    if c.operator == "lt":
        return v < threshold
    if c.operator == "lte":
        return v <= threshold
    if c.operator == "gt":
        return v > threshold
    if c.operator == "gte":
        return v >= threshold
    return False


def _evaluate_rule(rule: Rule, row: dict[str, Any]) -> tuple[bool, list[str]]:
    results = [(_passes(c, row), c) for c in rule.conditions.criteria]
    evidence = [f"{c.field} {c.operator} {c.value}" for ok, c in results if ok]
    if rule.conditions.combination == "or":
        matched = any(ok for ok, _ in results)
    else:
        matched = all(ok for ok, _ in results)
    return matched, evidence


def _signal_for(doc: RulesetDoc, rule: Rule, row: dict[str, Any], evidence: list[str]) -> Signal:
    return signal(
        target_id=str(row.get(doc.id_field, "")),
        label=rule.label,
        score=rule.score,
        evidence=evidence,
        features={"rule_id": rule.rule_id, **rule.output},
        subject={doc.id_field: row.get(doc.id_field)},
    )


def evaluate(
    doc: RulesetDoc, rows: list[dict[str, Any]], *, known_fields: set[str] | None = None
) -> list[Signal]:
    """Evaluate every rule against every row.

    A rule that can never fire (reported by :func:`_unsupported_reason`) is skipped, so a rule that
    is reported as unsupported never also emits a signal.
    """
    signals: list[Signal] = []
    for rule in doc.rules:
        if _unsupported_reason(rule, known_fields, id_field=doc.id_field):
            continue
        for row in rows:
            matched, evidence = _evaluate_rule(rule, row)
            if matched:
                signals.append(_signal_for(doc, rule, row, evidence))
    return signals


def run_ruleset(context: Context, ruleset_path: str | Path) -> BotResult:
    """Load (hot-read), validate, query the declared source, evaluate, and frame as a BotResult."""
    data = json.loads(Path(ruleset_path).read_text(encoding="utf-8"))
    report = validate_ruleset(data)
    if not report.valid or report.doc is None:
        raise RulesetError(f"invalid ruleset: {report.errors}")
    doc = report.doc

    query = doc.query or (f"SELECT * FROM {doc.source_table}" if doc.source_table else None)
    if not query:
        raise RulesetError("ruleset must declare 'source_table' or 'query'")
    rows = context.source.query(query)

    known = set(rows[0].keys()) if rows else None
    unsupported = [
        {"rule_id": r.rule_id, "reason": reason}
        for r in doc.rules
        if (reason := _unsupported_reason(r, known, id_field=doc.id_field))
    ]
    return result(
        evaluate(doc, rows, known_fields=known),
        label="ruleset",
        as_of=context.as_of,
        extra_metadata={"rules_total": len(doc.rules), "rules_unsupported": unsupported},
    )


# The data source and entity id are author-fixed; ruleset *proposals* may edit rules + descriptive
# metadata only — they cannot repoint source_table / query / id_field.
_EDITABLE_METADATA_KEYS = (
    "$schema_description",
    "task",
    "criteria_operators",
    "source_columns",
)


def merge_ruleset(base: dict[str, Any], proposed: dict[str, Any]) -> dict[str, Any]:
    """Overlay editable metadata from ``proposed`` onto ``base`` and replace ``rules``."""
    merged = dict(base)
    for key in _EDITABLE_METADATA_KEYS:
        if key in proposed:
            merged[key] = proposed[key]
    merged["rules"] = proposed.get("rules", [])
    return merged
