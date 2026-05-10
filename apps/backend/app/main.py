"""ParaSpell API entry point (NFR-12).

Wires together CORS middleware, the singleton SpellChecker, and all routers.
Run via Uvicorn (see Dockerfile CMD):

    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.engine.checker import get_checker
from app.routers import health, spell

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan: startup and shutdown handlers."""
    # Startup: initialize the spell checker
    logger.info("Starting up ParaSpell API...")
    checker = get_checker()
    logger.info("SpellChecker initialized.")
    yield
    # Shutdown: cleanup executor
    logger.info("Shutting down ParaSpell API...")
    checker.shutdown()
    logger.info("ParaSpell API shutdown complete.")


def create_app() -> FastAPI:
    application = FastAPI(
        title="ParaSpell API",
        version="0.1.0",
        description="Parallel spell-checker API — SRS NFR-12.",
        lifespan=lifespan,
    )

    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health.router)
    application.include_router(spell.router)

    @application.get("/", tags=["root"])
    def root() -> dict[str, str]:
        return {"name": "ParaSpell", "version": "0.1.0", "status": "ok"}

    return application


app = create_app()
