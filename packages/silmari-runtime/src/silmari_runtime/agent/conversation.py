# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Authoring conversation store: ordered messages per conversation (SQLite, thread-safe)."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool


class ConvBase(DeclarativeBase):
    pass


class MessageRow(ConvBase):
    __tablename__ = "authoring_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String, index=True)
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String, default="")
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String, default="")


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


class ConversationStore:
    def __init__(self, url: str = "sqlite://") -> None:
        _ensure_sqlite_dir(url)
        if _is_memory(url):
            self._engine = create_engine(
                url, future=True, poolclass=StaticPool, connect_args={"check_same_thread": False}
            )
        else:
            self._engine = create_engine(url, future=True)
        ConvBase.metadata.create_all(self._engine)
        self._lock = threading.RLock()

    def append(self, conversation_id: str, message: dict[str, Any]) -> None:
        with self._lock, Session(self._engine) as session:
            max_seq = (
                session.scalar(
                    select(func.max(MessageRow.seq)).where(
                        MessageRow.conversation_id == conversation_id
                    )
                )
                or 0
            )
            session.add(
                MessageRow(
                    conversation_id=conversation_id,
                    seq=max_seq + 1,
                    role=str(message.get("role", "")),
                    payload=json.dumps(message, ensure_ascii=False, default=str),
                    created_at=_now(),
                )
            )
            session.commit()

    def messages(self, conversation_id: str) -> list[dict[str, Any]]:
        """Ordered messages for a conversation, excluding system messages."""
        with self._lock, Session(self._engine) as session:
            stmt = (
                select(MessageRow)
                .where(MessageRow.conversation_id == conversation_id)
                .order_by(MessageRow.seq)
            )
            rows = session.scalars(stmt).all()
            return [json.loads(r.payload) for r in rows if r.role != "system"]

    def conversations(self) -> list[dict[str, str]]:
        """All conversations, most-recently-updated first."""
        with self._lock, Session(self._engine) as session:
            stmt = (
                select(
                    MessageRow.conversation_id,
                    func.max(MessageRow.created_at).label("updated_at"),
                )
                .group_by(MessageRow.conversation_id)
                .order_by(func.max(MessageRow.created_at).desc())
            )
            return [
                {"conversation_id": cid, "updated_at": updated}
                for cid, updated in session.execute(stmt).all()
            ]
