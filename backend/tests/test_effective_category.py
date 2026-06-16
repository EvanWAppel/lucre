from models import Transaction


def test_effective_category_uses_plaid_when_no_override():
    txn = Transaction(plaid_category="ENTERTAINMENT", user_category=None)
    assert txn.effective_category == "ENTERTAINMENT"


def test_user_category_overrides_plaid():
    txn = Transaction(plaid_category="ENTERTAINMENT", user_category="Streaming")
    assert txn.effective_category == "Streaming"


def test_effective_category_uncategorized_when_both_none():
    txn = Transaction(plaid_category=None, user_category=None)
    assert txn.effective_category == "Uncategorized"
