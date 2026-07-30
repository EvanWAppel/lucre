"""Ephemeral, per-visitor demo data stores (PRD H2).

Each demo session gets its own in-memory SQLite engine, seeded from a fixture and
torn down on idle expiry. These stores are completely separate from the real
database — a demo session can never read or write the owner's tables. The data
layer (H4) routes demo sessions here; the owner always uses the real engine.

In-memory + process-global is deliberate: the app runs as a single web process
(in-process scheduler), and demo data is meant to be throwaway, so a restart
wiping in-flight demo sandboxes is acceptable and on-spec ("ephemeral").
"""

import logging
import time
from collections.abc import Callable

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)

# A seed function receives a fresh session, adds rows, and returns; the manager
# commits. It need not (but may) commit itself.
SeedFn = Callable[[Session], None]

DEFAULT_IDLE_TTL_SECONDS = 30 * 60
DEFAULT_MAX_STORES = 100


class DemoStore:
    """One visitor's sandbox: an isolated engine + session factory."""

    def __init__(
        self,
        engine: Engine,
        session_factory: sessionmaker[Session],
        last_access: float,
    ) -> None:
        self.engine = engine
        self.session_factory = session_factory
        self.last_access = last_access


class DemoStoreManager:
    """Creates, tracks, and evicts per-session demo stores."""

    def __init__(
        self,
        seed: SeedFn | None = None,
        idle_ttl_seconds: int = DEFAULT_IDLE_TTL_SECONDS,
        max_stores: int = DEFAULT_MAX_STORES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._seed = seed
        self.idle_ttl_seconds = idle_ttl_seconds
        self.max_stores = max_stores
        self._clock = clock
        self._stores: dict[str, DemoStore] = {}

    def _build_store(self) -> DemoStore:
        import models  # noqa: F401 — registers models on Base
        from database import Base  # lazy: avoids a database <-> demo_store import cycle

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        if self._seed is not None:
            session = factory()
            try:
                self._seed(session)
                session.commit()
            finally:
                session.close()
        return DemoStore(engine, factory, self._clock())

    def get_or_create(self, session_id: str) -> DemoStore:
        self.evict_expired()
        store = self._stores.get(session_id)
        if store is None:
            if len(self._stores) >= self.max_stores:
                self._evict_lru()
            store = self._build_store()
            self._stores[session_id] = store
            logger.info("Created demo store %s (active=%d)", session_id, len(self._stores))
        store.last_access = self._clock()
        return store

    def _evict_lru(self) -> None:
        """Make room at the cap by dropping the least-recently-accessed store, so a
        new visitor is always admitted rather than refused."""
        oldest = min(self._stores.items(), key=lambda item: item[1].last_access)[0]
        self._dispose(oldest)
        logger.info("Evicted LRU demo store %s (cap %d reached)", oldest, self.max_stores)

    def evict_expired(self) -> None:
        cutoff = self._clock() - self.idle_ttl_seconds
        for session_id in [sid for sid, s in self._stores.items() if s.last_access < cutoff]:
            self._dispose(session_id)
            logger.info("Evicted idle demo store %s", session_id)

    def reset(self, session_id: str) -> None:
        self._dispose(session_id)

    def dispose_all(self) -> None:
        for session_id in list(self._stores):
            self._dispose(session_id)

    def active_count(self) -> int:
        return len(self._stores)

    def active_session_ids(self) -> set[str]:
        return set(self._stores)

    def _dispose(self, session_id: str) -> None:
        store = self._stores.pop(session_id, None)
        if store is not None:
            store.engine.dispose()


_manager: DemoStoreManager | None = None


def get_demo_store_manager() -> DemoStoreManager:
    """Process-wide demo store manager, seeded with the demo dataset. Overridable
    as a FastAPI dependency in tests."""
    global _manager
    if _manager is None:
        from services.demo_seed import demo_seed  # lazy: avoids an import cycle

        _manager = DemoStoreManager(seed=demo_seed)
    return _manager
