"""Metadata-only audit log for every data-source access.

Records *what* was accessed (kind, target table, row count, duration) and *when* / *by which
run* — never the SQL text or row data, so the audit log itself is not a sensitive-data surface.
Backed by SQLAlchemy; defaults to a shared in-memory SQLite database.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool


class AuditBase(DeclarativeBase):
    pass


class AuditRow(AuditBase):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String, index=True)
    run_id: Mapped[str] = mapped_column(String, index=True, default="")
    kind: Mapped[str] = mapped_column(String)
    target: Mapped[str] = mapped_column(String, default="")
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str] = mapped_column(String, default="ok")  # ok | denied | error


def _is_memory(url: str) -> bool:
    return url in ("sqlite://", "sqlite:///:memory:") or ":memory:" in url


def _ensure_sqlite_dir(url: str) -> None:
    prefix = "sqlite:///"
    if url.startswith(prefix):
        path = url[len(prefix) :]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class AuditLog:
    """Append-only audit store. Pass a SQLAlchemy URL; defaults to shared in-memory SQLite."""

    def __init__(self, url: str = "sqlite://") -> None:
        _ensure_sqlite_dir(url)
        if _is_memory(url):
            self._engine = create_engine(
                url,
                future=True,
                poolclass=StaticPool,
                connect_args={"check_same_thread": False},
            )
        else:
            self._engine = create_engine(url, future=True)
        AuditBase.metadata.create_all(self._engine)

    def record(
        self,
        kind: str,
        *,
        run_id: str = "",
        target: str = "",
        row_count: int = 0,
        duration_ms: int = 0,
        outcome: str = "ok",
    ) -> None:
        with Session(self._engine) as session:
            session.add(
                AuditRow(
                    ts=_now_iso(),
                    run_id=run_id,
                    kind=kind,
                    target=target,
                    row_count=row_count,
                    duration_ms=duration_ms,
                    outcome=outcome,
                )
            )
            session.commit()

    def entries(self) -> list[dict[str, Any]]:
        """Return all audit rows (oldest first) as plain dicts — for inspection and tests."""
        with Session(self._engine) as session:
            rows = session.scalars(select(AuditRow).order_by(AuditRow.id)).all()
            return [
                {
                    "id": r.id,
                    "ts": r.ts,
                    "run_id": r.run_id,
                    "kind": r.kind,
                    "target": r.target,
                    "row_count": r.row_count,
                    "duration_ms": r.duration_ms,
                    "outcome": r.outcome,
                }
                for r in rows
            ]
