import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import PlainTextResponse, Response

import demo_limits
from auth import DEMO_COOKIE, DEMO_MAX_AGE_SECONDS, SessionRole, current_role
from config import settings as app_settings
from database import init_db
from logging_setup import setup_logging
from routes import (
    alerts_preview,
    auth_routes,
    bills,
    demo,
    networth,
    pages,
    plaid_link,
    settings,
    spending,
    subscriptions,
    transactions,
)
from scheduler import build_scheduler

logger = logging.getLogger(__name__)

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


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

    @app.middleware("http")
    async def demo_session_middleware(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Resolve the session role for every request and, for demo (anonymous)
        visitors, mint/track an ephemeral demo-session id. get_db reads these off
        request.state to route owner traffic to the real DB and demo traffic to a
        sandboxed per-session store."""
        # The platform healthcheck (Railway `healthcheckPath = "/health"`) and
        # static assets are anonymous and don't touch get_db, so they must skip
        # demo-session logic entirely. Otherwise every cookieless healthcheck
        # mints a demo session and burns the demo create-limiter — repeated
        # healthchecks then hit 429 and Railway marks the deploy failed.
        path = request.url.path
        if path == "/health" or path.startswith("/static/"):
            return await call_next(request)
        role = current_role(request)
        request.state.role = role
        new_demo_id: str | None = None
        if role is SessionRole.DEMO:
            client_ip = request.client.host if request.client else "unknown"
            demo_id = request.cookies.get(DEMO_COOKIE)
            if not demo_id:
                if not demo_limits.create_limiter.allow(client_ip):
                    logger.warning("Demo session creation rate-limited for %s", client_ip)
                    return PlainTextResponse(
                        "Too many demo sessions from your network; try again shortly.",
                        status_code=429,
                    )
                demo_id = secrets.token_urlsafe(16)
                new_demo_id = demo_id
            if request.method not in _SAFE_METHODS and not demo_limits.write_limiter.allow(demo_id):
                logger.warning("Demo write rate-limited for session %s", demo_id)
                return PlainTextResponse("Too many requests; slow down.", status_code=429)
            request.state.demo_session_id = demo_id
        response = await call_next(request)
        if new_demo_id is not None:
            response.set_cookie(
                DEMO_COOKIE,
                new_demo_id,
                max_age=DEMO_MAX_AGE_SECONDS,
                httponly=True,
                secure=app_settings.cookie_secure,
                samesite="lax",
            )
        return response

    app.include_router(auth_routes.router)
    app.include_router(demo.router)
    app.include_router(alerts_preview.router)
    app.include_router(pages.router)
    app.include_router(plaid_link.router)
    app.include_router(transactions.router)
    app.include_router(spending.router)
    app.include_router(subscriptions.router)
    app.include_router(networth.router)
    app.include_router(bills.router)
    app.include_router(settings.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
