"""FastAPI app. Dependencies are injected via ``create_app(...)`` (for tests/embedding); the
module-level ``app`` builds in-memory defaults for ``uvicorn silmari_runtime.api.app:app``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..registry import load_registry
from ..review import ReviewStore
from ..sinks import EventBus, SubscriptionStore
from ..store import ResultStore
from .routers import (
    admin_router,
    bots_router,
    review_router,
    runs_router,
    subscriptions_router,
)

if TYPE_CHECKING:
    from silmari_core import DataSource

    from ..registry import BotRecord


def create_app(
    *,
    registry: dict[str, BotRecord] | None = None,
    store: ResultStore | None = None,
    reviews: ReviewStore | None = None,
    subscriptions: SubscriptionStore | None = None,
    bus: EventBus | None = None,
    source: DataSource | None = None,
    bots_dir: str = "bots",
) -> FastAPI:
    app = FastAPI(title="Silmari", version="0.1.0")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    app.state.bots_dir = bots_dir
    app.state.registry = registry if registry is not None else load_registry(bots_dir)
    app.state.store = store or ResultStore()
    app.state.reviews = reviews or ReviewStore()
    app.state.subscriptions = subscriptions or SubscriptionStore()
    app.state.bus = bus or EventBus()
    app.state.source = source

    for router in (bots_router, runs_router, review_router, subscriptions_router, admin_router):
        app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
