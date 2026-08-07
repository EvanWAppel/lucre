"""H4 — the data-layer routing guard (security-critical).

Proves a demo session's reads/writes hit only its sandboxed store and never the
real database, that demo sessions are isolated from each other, and that owner
traffic always uses the real DB.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import database
from auth import SessionRole
from database import Base, session_for_request
from models import Account, Item
from services.demo_store import DemoStoreManager


def _make_engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine


def _add_account(session: Session, plaid_id: str, name: str) -> None:
    item = Item(
        plaid_item_id=f"{plaid_id}-item", encrypted_access_token="x", institution_name="Bank"
    )
    session.add(item)
    session.flush()
    session.add(
        Account(
            item_id=item.id,
            plaid_account_id=plaid_id,
            name=name,
            account_type="depository",
            balance=1.0,
        )
    )
    session.commit()


def _demo_seed(session: Session) -> None:
    _add_account(session, "demo-only", "Demo Only")


@pytest.fixture
def owner_engine(monkeypatch):
    """Point the global SessionLocal at an isolated in-memory owner DB."""
    engine = _make_engine()
    monkeypatch.setattr(
        database, "SessionLocal", sessionmaker(bind=engine, autoflush=False, autocommit=False)
    )
    with database.SessionLocal() as s:
        _add_account(s, "owner-acct", "Owner Checking")
    yield engine
    engine.dispose()


def test_owner_uses_real_db(owner_engine):
    mgr = DemoStoreManager(seed=_demo_seed)
    db = session_for_request(SessionRole.OWNER, None, mgr)
    try:
        assert {a.name for a in db.query(Account).all()} == {"Owner Checking"}
    finally:
        db.close()


def test_demo_sees_only_its_sandbox(owner_engine):
    mgr = DemoStoreManager(seed=_demo_seed)
    db = session_for_request(SessionRole.DEMO, "sid-1", mgr)
    try:
        assert {a.name for a in db.query(Account).all()} == {"Demo Only"}
    finally:
        db.close()


def test_demo_write_never_touches_owner_db(owner_engine):
    mgr = DemoStoreManager(seed=_demo_seed)
    db = session_for_request(SessionRole.DEMO, "sid-1", mgr)
    try:
        _add_account(db, "demo-new", "Demo New Account")
    finally:
        db.close()
    with database.SessionLocal() as s:
        assert {a.name for a in s.query(Account).all()} == {"Owner Checking"}


def test_demo_sessions_isolated_from_each_other(owner_engine):
    mgr = DemoStoreManager(seed=_demo_seed)
    a = session_for_request(SessionRole.DEMO, "sid-a", mgr)
    try:
        _add_account(a, "a-only", "A Only")
    finally:
        a.close()
    b = session_for_request(SessionRole.DEMO, "sid-b", mgr)
    try:
        assert {acc.name for acc in b.query(Account).all()} == {"Demo Only"}
    finally:
        b.close()


def test_demo_without_session_id_fails_closed(owner_engine):
    mgr = DemoStoreManager(seed=_demo_seed)
    with pytest.raises(RuntimeError):
        session_for_request(SessionRole.DEMO, None, mgr)
