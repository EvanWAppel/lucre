from datetime import date

from plaid_client import (
    PlaidClient,
    build_link_token_request,
    get_plaid_client,
    normalize_accounts,
    normalize_transaction,
)


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


def test_normalize_transaction_maps_plaid_shape():
    raw = {
        "transaction_id": "txn-1",
        "account_id": "acct-1",
        "date": date(2026, 6, 1),
        "name": "NETFLIX.COM",
        "merchant_name": "Netflix",
        "amount": 15.49,
        "personal_finance_category": {"primary": "ENTERTAINMENT", "detailed": "ENTERTAINMENT_TV"},
        "pending": False,
    }
    assert normalize_transaction(raw) == {
        "plaid_transaction_id": "txn-1",
        "plaid_account_id": "acct-1",
        "date": date(2026, 6, 1),
        "name": "NETFLIX.COM",
        "merchant_name": "Netflix",
        "amount": 15.49,
        "plaid_category": "ENTERTAINMENT",
        "pending": False,
    }


def test_normalize_transaction_handles_iso_date_string_and_null_category():
    raw = {
        "transaction_id": "txn-2",
        "account_id": "acct-1",
        "date": "2026-06-02",
        "name": "UNKNOWN",
        "merchant_name": None,
        "amount": 5.0,
        "personal_finance_category": None,
        "pending": True,
    }
    result = normalize_transaction(raw)
    assert result["date"] == date(2026, 6, 2)
    assert result["plaid_category"] is None
    assert result["merchant_name"] is None


def test_link_token_request_includes_redirect_uri():
    request = build_link_token_request("https://app.example.com/link")
    assert request.to_dict()["redirect_uri"] == "https://app.example.com/link"


def test_link_token_request_omits_redirect_uri_when_unset():
    assert "redirect_uri" not in build_link_token_request(None).to_dict()
    assert "redirect_uri" not in build_link_token_request("").to_dict()


def test_get_plaid_client_returns_singleton():
    first = get_plaid_client()
    second = get_plaid_client()
    assert first is second
    assert isinstance(first, PlaidClient)
