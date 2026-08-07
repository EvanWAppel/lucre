"""H14 — full-stack isolation (security-critical).

Drives the real demo flow over HTTP with the *actual* role-aware get_db (no test
override) and proves the owner's real database is never written, while the demo
genuinely sees its seeded sandbox.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import database
from database import Base
from models import Account
from services.demo_seed import seed_demo_data
from services.demo_store import DemoStoreManager, get_demo_store_manager


def _seed(session: Session) -> None:
    seed_demo_data(session, date(2026, 6, 28))


@pytest.fixture
def isolated_client(monkeypatch):
    # A real, queryable owner database (stands in for production SQLite).
    owner_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(owner_engine)
    monkeypatch.setattr(
        database, "SessionLocal", sessionmaker(bind=owner_engine, autoflush=False, autocommit=False)
    )

    from main import app

    manager = DemoStoreManager(seed=_seed)
    app.dependency_overrides[get_demo_store_manager] = lambda: manager
    # NOTE: get_db is intentionally NOT overridden — the real router runs.
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client, owner_engine
    app.dependency_overrides.clear()


def test_demo_activity_never_writes_owner_db(isolated_client):
    client, owner_engine = isolated_client
    assert client.get("/dashboard").status_code == 200  # creates + seeds a sandbox
    client.post("/demo/connect", data={"institution": "Chase"})  # writes to the sandbox
    client.get("/transactions")
    with Session(owner_engine) as s:
        assert s.query(Account).count() == 0  # real DB completely untouched


def test_demo_actually_sees_its_seeded_sandbox(isolated_client):
    client, _ = isolated_client
    assert "netflix" in client.get("/subscriptions").text.lower()
    assert "Everyday Checking" in client.get("/dashboard").text


def test_owner_data_never_shown_to_demo(isolated_client):
    client, owner_engine = isolated_client
    # Plant a uniquely-named real account directly in the owner DB.
    with Session(owner_engine) as s:
        from models import Item

        item = Item(plaid_item_id="real", encrypted_access_token="x", institution_name="Real Bank")
        s.add(item)
        s.flush()
        s.add(
            Account(
                item_id=item.id,
                plaid_account_id="real-secret",
                name="SECRET_REAL_ACCOUNT",
                account_type="depository",
                balance=999999.0,
            )
        )
        s.commit()
    assert "SECRET_REAL_ACCOUNT" not in client.get("/dashboard").text
