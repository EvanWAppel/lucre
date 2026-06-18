from models import MerchantRule, Transaction
from services.rules import apply_rule_to_existing, upsert_rule
from services.sync import sync_transactions
from tests.conftest import TEST_PASSWORD
from tests.test_transactions_page import add_txn, seed


def login(client) -> None:
    client.post("/login", data={"password": TEST_PASSWORD})


def test_sync_stores_merchant_key(db_session, fake_plaid):
    from tests.test_transactions_sync import seed_item_with_accounts

    seed_item_with_accounts(db_session, fake_plaid)
    sync_transactions(db_session, fake_plaid)
    netflix = db_session.query(Transaction).filter_by(plaid_transaction_id="txn-netflix-1").one()
    assert netflix.merchant_key == "netflix"


def test_existing_rule_auto_categorizes_new_transactions_at_sync(db_session, fake_plaid):
    from tests.test_transactions_sync import seed_item_with_accounts

    seed_item_with_accounts(db_session, fake_plaid)
    upsert_rule(db_session, "netflix", "Streaming")

    sync_transactions(db_session, fake_plaid)

    netflix = db_session.query(Transaction).filter_by(plaid_transaction_id="txn-netflix-1").one()
    assert netflix.user_category == "Streaming"
    # A merchant without a rule is left to Plaid's category.
    grocery = db_session.query(Transaction).filter_by(plaid_transaction_id="txn-grocery-1").one()
    assert grocery.user_category is None


def test_upsert_rule_is_unique_per_key(db_session):
    upsert_rule(db_session, "netflix", "Streaming")
    upsert_rule(db_session, "netflix", "Entertainment")
    rules = db_session.query(MerchantRule).all()
    assert len(rules) == 1
    assert rules[0].category == "Entertainment"


def test_apply_rule_to_existing_retroactively(db_session, fake_plaid):
    checking, _ = seed(db_session, fake_plaid)
    add_txn(db_session, checking, "s1", 1, "STARBUCKS #111", 5.0, plaid_cat="FOOD_AND_DRINK")
    add_txn(db_session, checking, "s2", 2, "STARBUCKS #222", 6.0, plaid_cat="FOOD_AND_DRINK")
    # merchant_key isn't set by the manual add helper; the service computes it.

    count = apply_rule_to_existing(db_session, "starbucks", "Coffee")

    assert count == 2
    for tid in ("s1", "s2"):
        txn = db_session.query(Transaction).filter_by(plaid_transaction_id=tid).one()
        assert txn.user_category == "Coffee"


def test_recategorize_with_apply_to_merchant_creates_rule_and_backfills(
    client, db_session, fake_plaid
):
    login(client)
    checking, _ = seed(db_session, fake_plaid)
    t1 = add_txn(db_session, checking, "s1", 1, "STARBUCKS #111", 5.0, plaid_cat="FOOD_AND_DRINK")
    add_txn(db_session, checking, "s2", 2, "STARBUCKS #222", 6.0, plaid_cat="FOOD_AND_DRINK")

    response = client.patch(
        f"/api/transactions/{t1.id}/category",
        data={"category": "Coffee", "apply_to_merchant": "on"},
    )

    assert response.status_code == 200
    rule = db_session.query(MerchantRule).filter_by(merchant_key="starbucks").one()
    assert rule.category == "Coffee"
    # Both Starbucks transactions recategorized, despite different store numbers.
    for tid in ("s1", "s2"):
        txn = db_session.query(Transaction).filter_by(plaid_transaction_id=tid).one()
        assert txn.user_category == "Coffee"
