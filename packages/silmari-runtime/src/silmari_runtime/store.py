"""Run result store: per-run lifecycle (running → completed/failed) + persisted signals.

Backed by SQLAlchemy/SQLite; defaults to a shared in-memory database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool

from .context import BotResult

STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


class StoreBase(DeclarativeBase):
    pass


class RunRow(StoreBase):
    __tablename__ = "bot_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    bot_id: Mapped[str] = mapped_column(String, index=True)
    as_of: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[str] = mapped_column(String, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    data_json: Mapped[str] = mapped_column(Text, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String, default=STATUS_COMPLETED, index=True)
    started_at: Mapped[str] = mapped_column(String, default="")
    finished_at: Mapped[str] = mapped_column(String, default="")
    error: Mapped[str] = mapped_column(Text, default="")


@dataclass
class StoredRun:
    run_id: str
    bot_id: str
    as_of: str
    created_at: str
    summary: str
    data: list[dict[str, Any]]
    metadata: dict[str, Any]
    status: str = STATUS_COMPLETED
    started_at: str = ""
    finished_at: str = ""
    error: str = ""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _is_memory(url: str) -> bool:
    return url in ("sqlite://", "sqlite:///:memory:") or ":memory:" in url


def _ensure_sqlite_dir(url: str) -> None:
    prefix = "sqlite:///"
    if url.startswith(prefix):
        path = url[len(prefix) :]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)


def _to_stored(row: RunRow) -> StoredRun:
    return StoredRun(
        run_id=row.run_id,
        bot_id=row.bot_id,
        as_of=row.as_of,
        created_at=row.created_at,
        summary=row.summary,
        data=json.loads(row.data_json or "[]"),
        metadata=json.loads(row.metadata_json or "{}"),
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        error=row.error,
    )


class ResultStore:
    def __init__(self, url: str = "sqlite://") -> None:
        _ensure_sqlite_dir(url)
        if _is_memory(url):
            self._engine = create_engine(
                url, future=True, poolclass=StaticPool, connect_args={"check_same_thread": False}
            )
        else:
            self._engine = create_engine(url, future=True)
        StoreBase.metadata.create_all(self._engine)

    def create_running(self, bot_id: str, run_id: str, as_of: str) -> StoredRun:
        now = _now()
        with Session(self._engine) as session:
            row = RunRow(
                run_id=run_id,
                bot_id=bot_id,
                as_of=as_of,
                created_at=now,
                status=STATUS_RUNNING,
                started_at=now,
            )
            session.add(row)
            session.commit()
            return _to_stored(row)

    def mark_completed(self, run_id: str, result: BotResult) -> StoredRun:
        with Session(self._engine) as session:
            row = session.get(RunRow, run_id)
            if row is None:
                raise KeyError(run_id)
            row.summary = result.summary
            row.data_json = json.dumps(result.data, ensure_ascii=False)
            row.metadata_json = json.dumps(result.metadata, ensure_ascii=False)
            row.status = STATUS_COMPLETED
            row.finished_at = _now()
            session.commit()
            return _to_stored(row)

    def mark_failed(self, run_id: str, error: str) -> StoredRun:
        with Session(self._engine) as session:
            row = session.get(RunRow, run_id)
            if row is None:
                raise KeyError(run_id)
            row.status = STATUS_FAILED
            row.error = error
            row.finished_at = _now()
            session.commit()
            return _to_stored(row)

    def get(self, bot_id: str, run_id: str) -> StoredRun | None:
        with Session(self._engine) as session:
            row = session.get(RunRow, run_id)
            if row is None or row.bot_id != bot_id:
                return None
            return _to_stored(row)

    def latest(self, bot_id: str) -> StoredRun | None:
        runs = self.history(bot_id, limit=1, status=STATUS_COMPLETED)
        return runs[0] if runs else None

    def history(
        self, bot_id: str, limit: int = 20, *, status: str | None = None
    ) -> list[StoredRun]:
        with Session(self._engine) as session:
            stmt = select(RunRow).where(RunRow.bot_id == bot_id)
            if status is not None:
                stmt = stmt.where(RunRow.status == status)
            stmt = stmt.order_by(RunRow.created_at.desc(), RunRow.run_id.desc()).limit(limit)
            return [_to_stored(r) for r in session.scalars(stmt).all()]
