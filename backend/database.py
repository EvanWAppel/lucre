import logging
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

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


def init_db() -> None:
    """Create all tables. Called on app startup."""
    import models  # noqa: F401 — ensures models are registered

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")
