from plaid_client import PlaidClient, get_plaid_client, normalize_accounts


def test_normalize_accounts_maps_plaid_shape():
    raw = [
        {
            "account_id": "abc123",
            "name": "Everyday Checking",
            "type": "depository",
            "subtype": "checking",
            "balances": {"current": 1500.25, "available": 1400.00},
        },
        {
            "account_id": "def456",
            "name": "Travel Card",
            "type": "credit",
            "subtype": None,
            "balances": {"current": 432.10},
        },
    ]
    assert normalize_accounts(raw) == [
        {
            "plaid_account_id": "abc123",
            "name": "Everyday Checking",
            "type": "depository",
            "subtype": "checking",
            "balance": 1500.25,
        },
        {
            "plaid_account_id": "def456",
            "name": "Travel Card",
            "type": "credit",
            "subtype": None,
            "balance": 432.10,
        },
    ]


def test_get_plaid_client_returns_singleton():
    first = get_plaid_client()
    second = get_plaid_client()
    assert first is second
    assert isinstance(first, PlaidClient)
