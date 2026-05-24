from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import router as api_router
from .config import get_settings
from .db import migrate, session
from .services.scheduler import start_scheduler
from .webhook import router as webhook_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    with session(settings.db_path) as db:
        migrate(db)
    scheduler = None
    if settings.scheduler_autostart:
        scheduler = start_scheduler(settings)
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(
        title="TradeNest",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.include_router(webhook_router)
    app.include_router(api_router)

    return app


app = create_app()
