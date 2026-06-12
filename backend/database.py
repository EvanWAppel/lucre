import logging
from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings

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


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
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
