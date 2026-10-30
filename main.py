"""FastAPI application."""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from fovea import PRODUCT_NAME, __version__
from fovea.api.routes import router
from fovea.config import get_settings
from fovea.logging_setup import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    app = FastAPI(
        title=PRODUCT_NAME,
        version=__version__,
        description=(
            "Evidence grounded decision support for NHS eye treatment. Every factual sentence is cited, every "
            "clinical figure is checked against its source, and safety critical numbers come from deterministic tools."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-Id"] = uuid.uuid4().hex
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
        response.headers["Server-Timing"] = f"app;dur={(time.perf_counter() - started) * 1000:.1f}"
        return response

    app.include_router(router)
    return app


app = create_app()
