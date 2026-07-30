import logging
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from auth import SessionRole
from config import settings
from services.demo_store import DemoStoreManager, get_demo_store_manager

logger = logging.getLogger(__name__)


def build_engine(database_url: str) -> Engine:
    connect_args = {}
    if database_url.startswith("sqlite"):
        # FastAPI handles requests across threads; SQLite connections must allow that.
        connect_args["check_same_thread"] = False
    new_engine = create_engine(database_url, connect_args=connect_args)

    if database_url.startswith("sqlite"):

        @event.listens_for(new_engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return new_engine


engine = build_engine(settings.database_url)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def session_for_request(
    role: SessionRole, demo_session_id: str | None, demo_manager: DemoStoreManager
) -> Session:
    """Pick the backing store from the session role. This is the single choke point
    that keeps demo traffic off the real database: an OWNER gets the real
    SessionLocal; everyone else gets their throwaway per-session demo store, which
    can never reach the owner's tables."""
    if role is SessionRole.OWNER:
        return SessionLocal()
    if demo_session_id is None:
        raise RuntimeError("demo request reached the data layer without a demo session id")
    return demo_manager.get_or_create(demo_session_id).session_factory()


def get_db(
    request: Request,
    demo_manager: Annotated[DemoStoreManager, Depends(get_demo_store_manager)],
) -> Generator[Session, None, None]:
    # The demo-session middleware sets these; default to OWNER so any non-HTTP or
    # mis-wired caller fails closed onto the real DB only when truly authenticated.
    role: SessionRole = getattr(request.state, "role", SessionRole.OWNER)
    demo_session_id: str | None = getattr(request.state, "demo_session_id", None)
    db = session_for_request(role, demo_session_id, demo_manager)
    try:
        yield db
    except Exception:
        logger.exception("Database session error; rolling back")
        db.rollback()
        raise
    finally:
        db.close()


def init_db(target_engine: Engine | None = None) -> None:
    """Create all tables. Called on app startup."""
    import models  # noqa: F401 — ensures models are registered

    Base.metadata.create_all(bind=target_engine or engine)
    logger.info("Database tables created/verified")
