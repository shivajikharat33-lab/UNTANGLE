"""UNTANGLE HTTP application.

Run from the backend directory:

    uvicorn app.main:app --reload
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.health import router as health_router
from app.api.edits import router as edits_router
from app.api.jobs import router as jobs_router
from app.api.middleware import RequestIdMiddleware
from app.config import APP_VERSION, Settings
from app.database import init_db, make_engine

logger = logging.getLogger("untangle")


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Create the tables when the database can be opened. Keep serving either way."""
    engine = application.state.engine
    if engine is not None:
        try:
            init_db(engine)
        except Exception:
            logger.exception("database startup failed; /api/health will report database failed")
    yield
    if engine is not None:
        engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API. Tests pass their own Settings so they do not touch the dev database."""
    settings = settings or Settings()
    application = FastAPI(title="UNTANGLE", version=APP_VERSION, lifespan=lifespan)
    application.state.settings = settings
    try:
        application.state.engine = make_engine(settings.database_url)
    except Exception:
        logger.exception("database engine could not be created")
        application.state.engine = None

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    application.add_middleware(RequestIdMiddleware)
    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(jobs_router)
    application.include_router(edits_router)
    return application


app = create_app()
