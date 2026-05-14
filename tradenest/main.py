from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import get_settings
from .db import migrate, session
from .webhook import router as webhook_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    with session(settings.db_path) as db:
        migrate(db)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="TradeNest", lifespan=lifespan)
    app.include_router(webhook_router)

    return app


app = create_app()
