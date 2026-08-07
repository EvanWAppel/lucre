from sqlalchemy.orm import Session

from models import Account, Item
from services.demo_store import DemoStoreManager


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _seed(session: Session) -> None:
    """Minimal seed: one item + one account. The manager commits."""
    item = Item(
        plaid_item_id="demo-item",
        encrypted_access_token="x",
        institution_name="Demo Bank",
    )
    session.add(item)
    session.flush()  # populate item.id for the FK
    session.add(
        Account(
            item_id=item.id,
            plaid_account_id="demo-acct",
            name="Demo Checking",
            account_type="depository",
            balance=100.0,
        )
    )


def test_store_is_seeded():
    mgr = DemoStoreManager(seed=_seed)
    store = mgr.get_or_create("sid-1")
    with store.session_factory() as s:
        assert s.query(Account).count() == 1


def test_two_sessions_are_independent():
    mgr = DemoStoreManager(seed=_seed)
    a = mgr.get_or_create("sid-a")
    b = mgr.get_or_create("sid-b")
    with a.session_factory() as s:
        s.add(Item(plaid_item_id="extra", encrypted_access_token="x", institution_name="Extra"))
        s.commit()
    with a.session_factory() as s:
        assert s.query(Item).count() == 2
    with b.session_factory() as s:
        assert s.query(Item).count() == 1  # B is untouched by A's write


def test_get_or_create_returns_same_store_for_same_id():
    mgr = DemoStoreManager(seed=_seed)
    assert mgr.get_or_create("sid") is mgr.get_or_create("sid")


def test_idle_expiry_frees_the_store():
    clock = FakeClock()
    mgr = DemoStoreManager(seed=_seed, idle_ttl_seconds=1800, clock=clock)
    mgr.get_or_create("sid")
    assert mgr.active_count() == 1
    clock.now += 1801
    mgr.evict_expired()
    assert mgr.active_count() == 0


def test_access_refreshes_idle_timer():
    clock = FakeClock()
    mgr = DemoStoreManager(seed=_seed, idle_ttl_seconds=1800, clock=clock)
    mgr.get_or_create("sid")
    clock.now += 1000
    mgr.get_or_create("sid")  # touch within the window
    clock.now += 1000  # 2000s since create, only 1000s since last touch
    mgr.evict_expired()
    assert mgr.active_count() == 1


def test_reset_gives_a_fresh_store():
    mgr = DemoStoreManager(seed=_seed)
    store = mgr.get_or_create("sid")
    with store.session_factory() as s:
        s.add(Item(plaid_item_id="extra", encrypted_access_token="x", institution_name="Extra"))
        s.commit()
    mgr.reset("sid")
    assert mgr.active_count() == 0
    fresh = mgr.get_or_create("sid")
    with fresh.session_factory() as s:
        assert s.query(Item).count() == 1  # back to seed-only
