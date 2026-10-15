"""UNTANGLE HTTP application.

Run from the backend directory:

    uvicorn app.main:app --reload
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.access_tokens import AccessRegistry
from app.api.access import router as access_router
from app.api.errors import register_exception_handlers
from app.api.health import router as health_router
from app.api.edits import router as edits_router
from app.api.jobs import router as jobs_router
from app.api.middleware import RequestIdMiddleware
from app.api.probes import router as probes_router
from app.config import APP_VERSION, Settings
from app.database import ensure_sqlite_parent, init_db, make_engine
from app.http_guards import GuardMiddleware, SecurityHeadersMiddleware
from app.logging_config import configure_logging
from app.rate_limit import RateLimiter
from app.services.pdf_raster import set_ocr_in_build

logger = logging.getLogger("untangle")


def _ensure_storage(settings: Settings) -> None:
    """Create upload/cache folders and the SQLite parent so Render can write on first boot."""
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.cache_dir).mkdir(parents=True, exist_ok=True)
    ensure_sqlite_parent(settings.database_url)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Create the tables when the database can be opened. Keep serving either way."""
    engine = application.state.engine
    settings = application.state.settings
    try:
        _ensure_storage(settings)
    except Exception:
        logger.exception("storage folders could not be created")
    if engine is not None:
        try:
            init_db(engine)
        except Exception:
            logger.exception("database startup failed; /api/health will report database failed")
        if settings.public_demo_mode:
            try:
                from app.services.demo_seed import seed_demo

                await seed_demo(settings, engine)
            except Exception:
                logger.exception("demo seed failed")
    yield
    if engine is not None:
        engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API. Tests pass their own Settings so they do not touch the dev database."""
    settings = settings or Settings()
    configure_logging(settings.log_level)
    set_ocr_in_build(settings.ocr_in_build)
    try:
        _ensure_storage(settings)
    except Exception:
        logger.exception("storage folders could not be created before the engine opens")
    application = FastAPI(title="UNTANGLE", version=APP_VERSION, lifespan=lifespan)
    application.state.settings = settings
    application.state.access_tokens = AccessRegistry()
    application.state.rate_limiter = RateLimiter()
    try:
        ensure_sqlite_parent(settings.database_url)
        application.state.engine = make_engine(settings.database_url)
    except Exception:
        logger.exception("database engine could not be created")
        application.state.engine = None

    # Last added runs first. Request id stays outside so every response can carry it.
    application.add_middleware(GuardMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(RequestIdMiddleware)
    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(probes_router)
    application.include_router(access_router)
    application.include_router(jobs_router)
    application.include_router(edits_router)
    return application


app = create_app()
