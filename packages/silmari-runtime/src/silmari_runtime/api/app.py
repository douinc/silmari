# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
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
    data_router,
    review_router,
    runs_router,
    subscriptions_router,
)

if TYPE_CHECKING:
    from silmari_core import DataSource

    from ..registry import BotRecord

#: Public source repository. Silmari is licensed under AGPL-3.0-or-later, whose §13 requires that
#: users interacting with this service over a network be offered its Corresponding Source. We
#: surface this URL in the OpenAPI metadata (``/docs``, ``/openapi.json``) so that offer is visible.
SOURCE_URL = "https://github.com/douinc/silmari"


def create_app(
    *,
    registry: dict[str, BotRecord] | None = None,
    store: ResultStore | None = None,
    reviews: ReviewStore | None = None,
    subscriptions: SubscriptionStore | None = None,
    bus: EventBus | None = None,
    source: DataSource | None = None,
    bots_dir: str = "bots",
    cors_origins: list[str] | None = None,
    ui_dir: str | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Silmari",
        version="0.1.0",
        description=(
            "Governed, read-only, scoped, audited data access for LLM agents.\n\n"
            "Silmari is free software, licensed under the GNU Affero General Public License "
            "v3 or later (AGPL-3.0-or-later). In accordance with AGPL §13, the complete "
            f"Corresponding Source for this running service is available at {SOURCE_URL}."
        ),
        license_info={
            "name": "AGPL-3.0-or-later",
            "url": "https://www.gnu.org/licenses/agpl-3.0.html",
        },
    )
    # No CORS by default (same-origin only). The API is unauthenticated (see SECURITY.md) — pass an
    # explicit allow-list to enable cross-origin access, and deploy it behind auth.
    if cors_origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=cors_origins, allow_methods=["*"], allow_headers=["*"]
        )

    app.state.bots_dir = bots_dir
    app.state.registry = registry if registry is not None else load_registry(bots_dir)
    app.state.store = store or ResultStore()
    app.state.reviews = reviews or ReviewStore()
    app.state.subscriptions = subscriptions or SubscriptionStore()
    app.state.bus = bus or EventBus()
    app.state.source = source

    for router in (
        bots_router,
        runs_router,
        review_router,
        subscriptions_router,
        admin_router,
        data_router,
    ):
        app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    if ui_dir:
        # Serve a static reference UI same-origin (no CORS needed). Mounted last so API routes win.
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=ui_dir, html=True), name="ui")

    return app


app = create_app()
