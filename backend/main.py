import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from database import init_db
from logging_setup import setup_logging
from routes import auth_routes, pages, plaid_link, spending, transactions
from scheduler import build_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    scheduler = None
    if os.environ.get("LUCRE_ENABLE_SCHEDULER") == "1":
        scheduler = build_scheduler()
        scheduler.start()
        logger.info("Daily sync scheduler started")
    yield
    if scheduler is not None:
        scheduler.shutdown()


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="Lucre", lifespan=lifespan)
    app.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).parent / "static")),
        name="static",
    )
    app.include_router(auth_routes.router)
    app.include_router(pages.router)
    app.include_router(plaid_link.router)
    app.include_router(transactions.router)
    app.include_router(spending.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
