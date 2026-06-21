import logging
from datetime import date
from typing import Protocol

import plaid
from plaid.api import plaid_api
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.link_token_transactions import LinkTokenTransactions
from plaid.model.products import Products
from plaid.model.transactions_sync_request import TransactionsSyncRequest

from config import settings

logger = logging.getLogger(__name__)

_HOSTS = {
    "sandbox": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}

# How far back Plaid backfills transactions on first connect. 24 months so annual
# subscriptions are seen at least twice and category trends are useful immediately.
TRANSACTIONS_DAYS_REQUESTED = 730


class PlaidClientLike(Protocol):
    """What routes/services need from a Plaid client; FakePlaidClient satisfies it too."""

    def create_link_token(self) -> str: ...

    def exchange_public_token(self, public_token: str) -> dict: ...

    def get_accounts(self, access_token: str) -> list[dict]: ...

    def transactions_sync(self, access_token: str, cursor: str | None) -> dict: ...


def build_link_token_request(redirect_uri: str | None = None) -> LinkTokenCreateRequest:
    """Build the /link/token/create request. A non-empty redirect_uri is included so
    OAuth institutions (Chase et al.) can hand the browser back to /link; it must be
    registered in the Plaid dashboard or Plaid rejects the request."""
    kwargs = {
        "user": LinkTokenCreateRequestUser(client_user_id="lucre-single-user"),
        "client_name": "Lucre",
        "products": [Products("transactions")],
        "transactions": LinkTokenTransactions(days_requested=TRANSACTIONS_DAYS_REQUESTED),
        "country_codes": [CountryCode("US")],
        "language": "en",
    }
    if redirect_uri:
        kwargs["redirect_uri"] = redirect_uri
    return LinkTokenCreateRequest(**kwargs)


def normalize_accounts(accounts: list[dict]) -> list[dict]:
    """Map Plaid's /accounts/get account dicts to our internal shape."""
    return [
        {
            "plaid_account_id": account["account_id"],
            "name": account["name"],
            "type": str(account["type"]),
            "subtype": str(account["subtype"]) if account.get("subtype") is not None else None,
            "balance": account["balances"]["current"],
        }
        for account in accounts
    ]


def _to_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def normalize_transaction(txn: dict) -> dict:
    """Map a Plaid /transactions/sync transaction dict to our internal shape."""
    pfc = txn.get("personal_finance_category")
    return {
        "plaid_transaction_id": txn["transaction_id"],
        "plaid_account_id": txn["account_id"],
        "date": _to_date(txn["date"]),
        "name": txn["name"],
        "merchant_name": txn.get("merchant_name"),
        "amount": txn["amount"],
        "plaid_category": pfc["primary"] if pfc else None,
        "pending": txn["pending"],
    }


class PlaidClient:
    """Thin wrapper over the Plaid SDK. Tests use tests.conftest.FakePlaidClient instead."""

    def __init__(self) -> None:
        configuration = plaid.Configuration(
            host=_HOSTS[settings.plaid_env],
            api_key={"clientId": settings.plaid_client_id, "secret": settings.plaid_secret},
        )
        self._api = plaid_api.PlaidApi(plaid.ApiClient(configuration))

    def create_link_token(self) -> str:
        request = build_link_token_request(settings.plaid_redirect_uri or None)
        response = self._api.link_token_create(request)
        return response["link_token"]

    def exchange_public_token(self, public_token: str) -> dict:
        request = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = self._api.item_public_token_exchange(request)
        return {"item_id": response["item_id"], "access_token": response["access_token"]}

    def get_accounts(self, access_token: str) -> list[dict]:
        request = AccountsGetRequest(access_token=access_token)
        response = self._api.accounts_get(request).to_dict()
        return normalize_accounts(response["accounts"])

    def transactions_sync(self, access_token: str, cursor: str | None) -> dict:
        # Plaid wants an empty string, not null, for the first page.
        request = TransactionsSyncRequest(access_token=access_token, cursor=cursor or "")
        response = self._api.transactions_sync(request).to_dict()
        return {
            "added": [normalize_transaction(t) for t in response["added"]],
            "modified": [normalize_transaction(t) for t in response["modified"]],
            "removed": [r["transaction_id"] for r in response["removed"]],
            "next_cursor": response["next_cursor"],
            "has_more": response["has_more"],
        }


_client: PlaidClient | None = None


def get_plaid_client() -> PlaidClient:
    """FastAPI dependency. Overridden with FakePlaidClient in tests."""
    global _client
    if _client is None:
        _client = PlaidClient()
    return _client
