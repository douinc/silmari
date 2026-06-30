"""Review loop: per-case accept/reject/note decisions + threshold tuning (precision/recall/F1).

A "case" is one emitted signal within a run, addressed by its index in the run's data. "pending"
is the absence of a decision row. Tuning replays labeled decisions across score thresholds and
recommends the F1-best threshold (ties broken toward a higher threshold = fewer flagged cases).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool

from .store import ResultStore

DECISIONS = ("accepted", "rejected", "pending")
_SEP = "\x1f"


class ReviewBase(DeclarativeBase):
    pass


class ReviewRow(ReviewBase):
    __tablename__ = "review_decisions"

    key: Mapped[str] = mapped_column(String, primary_key=True)  # bot\x1frun\x1fcase
    bot_id: Mapped[str] = mapped_column(String, index=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    case_id: Mapped[str] = mapped_column(String)
    decision: Mapped[str] = mapped_column(String, default="pending")
    note: Mapped[str] = mapped_column(Text, default="")
    reviewer: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[str] = mapped_column(String, default="")


@dataclass
class ReviewDecision:
    bot_id: str
    run_id: str
    case_id: str
    decision: str
    note: str
    reviewer: str
    updated_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _key(bot_id: str, run_id: str, case_id: str) -> str:
    return _SEP.join((bot_id, run_id, case_id))


def _is_memory(url: str) -> bool:
    return url in ("sqlite://", "sqlite:///:memory:") or ":memory:" in url


def _ensure_sqlite_dir(url: str) -> None:
    prefix = "sqlite:///"
    if url.startswith(prefix):
        path = url[len(prefix) :]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)


def _to_decision(row: ReviewRow) -> ReviewDecision:
    return ReviewDecision(
        bot_id=row.bot_id,
        run_id=row.run_id,
        case_id=row.case_id,
        decision=row.decision,
        note=row.note,
        reviewer=row.reviewer,
        updated_at=row.updated_at,
    )


def build_cases(data: list[dict[str, Any]]) -> list[tuple[str, float | None, dict[str, Any]]]:
    """Map a run's records to ``(case_id, score, record)``; case_id is the record's index."""
    cases: list[tuple[str, float | None, dict[str, Any]]] = []
    for i, record in enumerate(data):
        score = record.get("score")
        cases.append((str(i), score if isinstance(score, int | float) else None, record))
    return cases


class ReviewStore:
    def __init__(self, url: str = "sqlite://") -> None:
        _ensure_sqlite_dir(url)
        if _is_memory(url):
            self._engine = create_engine(
                url, future=True, poolclass=StaticPool, connect_args={"check_same_thread": False}
            )
        else:
            self._engine = create_engine(url, future=True)
        ReviewBase.metadata.create_all(self._engine)
        self._lock = threading.RLock()

    def set_decision(
        self,
        bot_id: str,
        run_id: str,
        case_id: str,
        decision: str,
        *,
        note: str = "",
        reviewer: str = "",
    ) -> ReviewDecision:
        if decision not in DECISIONS:
            raise ValueError(f"unknown decision {decision!r}; expected one of {DECISIONS}")
        with self._lock, Session(self._engine) as session:
            row = ReviewRow(
                key=_key(bot_id, run_id, case_id),
                bot_id=bot_id,
                run_id=run_id,
                case_id=case_id,
                decision=decision,
                note=note,
                reviewer=reviewer,
                updated_at=_now(),
            )
            session.merge(row)
            session.commit()
            return _to_decision(row)

    def get(self, bot_id: str, run_id: str, case_id: str) -> ReviewDecision | None:
        with self._lock, Session(self._engine) as session:
            row = session.get(ReviewRow, _key(bot_id, run_id, case_id))
            return _to_decision(row) if row is not None else None

    def decisions_for_run(self, bot_id: str, run_id: str) -> dict[str, ReviewDecision]:
        with self._lock, Session(self._engine) as session:
            stmt = select(ReviewRow).where(ReviewRow.bot_id == bot_id, ReviewRow.run_id == run_id)
            return {r.case_id: _to_decision(r) for r in session.scalars(stmt).all()}

    def tally(self, bot_id: str, run_id: str, total_cases: int | None = None) -> dict[str, int]:
        decisions = self.decisions_for_run(bot_id, run_id)
        accepted = sum(1 for d in decisions.values() if d.decision == "accepted")
        rejected = sum(1 for d in decisions.values() if d.decision == "rejected")
        tally = {"accepted": accepted, "rejected": rejected, "reviewed": accepted + rejected}
        if total_cases is not None:
            tally["total"] = total_cases
            tally["pending"] = total_cases - tally["reviewed"]
        return tally


# --------------------------------------------------------------------------- tuning


@dataclass
class LabeledCase:
    run_id: str
    case_id: str
    score: float | None
    accepted: bool


@dataclass
class ThresholdPoint:
    threshold: float
    flagged: int
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float


@dataclass
class TuningReport:
    bot_id: str
    labeled: int
    accepted: int
    rejected: int
    unscored: int
    points: list[ThresholdPoint] = field(default_factory=list)
    recommended: ThresholdPoint | None = None


def collect_labels(
    store: ResultStore, reviews: ReviewStore, bot_id: str, *, limit: int = 50
) -> list[LabeledCase]:
    labels: list[LabeledCase] = []
    for run in store.history(bot_id, limit=limit):
        decisions = reviews.decisions_for_run(bot_id, run.run_id)
        for case_id, score, _record in build_cases(run.data):
            decision = decisions.get(case_id)
            if decision is None or decision.decision == "pending":
                continue
            labels.append(
                LabeledCase(run.run_id, case_id, score, decision.decision == "accepted")
            )
    return labels


def tune(bot_id: str, labels: list[LabeledCase]) -> TuningReport:
    scored = [c for c in labels if c.score is not None]
    accepted = sum(1 for c in labels if c.accepted)
    rejected = sum(1 for c in labels if not c.accepted)
    accepted_scored = sum(1 for c in scored if c.accepted)

    points: list[ThresholdPoint] = []
    for threshold in sorted({c.score for c in scored if c.score is not None}):
        flagged = [c for c in scored if c.score is not None and c.score >= threshold]
        tp = sum(1 for c in flagged if c.accepted)
        fp = len(flagged) - tp
        fn = accepted_scored - tp
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        points.append(
            ThresholdPoint(
                threshold=round(threshold, 6),
                flagged=len(flagged),
                tp=tp,
                fp=fp,
                fn=fn,
                precision=round(precision, 4),
                recall=round(recall, 4),
                f1=round(f1, 4),
            )
        )
    recommended = max(points, key=lambda p: (p.f1, p.threshold)) if points else None
    return TuningReport(
        bot_id=bot_id,
        labeled=len(labels),
        accepted=accepted,
        rejected=rejected,
        unscored=len(labels) - len(scored),
        points=points,
        recommended=recommended,
    )


def tuning_report(
    store: ResultStore, reviews: ReviewStore, bot_id: str, *, limit: int = 50
) -> TuningReport:
    return tune(bot_id, collect_labels(store, reviews, bot_id, limit=limit))
