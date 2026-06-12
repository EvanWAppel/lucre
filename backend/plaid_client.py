import logging
from typing import Protocol

import plaid
from plaid.api import plaid_api
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products

from config import settings

logger = logging.getLogger(__name__)

_HOSTS = {
    "sandbox": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}


class PlaidClientLike(Protocol):
    """What routes/services need from a Plaid client; FakePlaidClient satisfies it too."""

    def create_link_token(self) -> str: ...

    def exchange_public_token(self, public_token: str) -> dict: ...

    def get_accounts(self, access_token: str) -> list[dict]: ...


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


class PlaidClient:
    """Thin wrapper over the Plaid SDK. Tests use tests.conftest.FakePlaidClient instead."""

    def __init__(self) -> None:
        configuration = plaid.Configuration(
            host=_HOSTS[settings.plaid_env],
            api_key={"clientId": settings.plaid_client_id, "secret": settings.plaid_secret},
        )
        self._api = plaid_api.PlaidApi(plaid.ApiClient(configuration))

    def create_link_token(self) -> str:
        request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id="lucre-single-user"),
            client_name="Lucre",
            products=[Products("transactions")],
            country_codes=[CountryCode("US")],
            language="en",
        )
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


_client: PlaidClient | None = None


def get_plaid_client() -> PlaidClient:
    """FastAPI dependency. Overridden with FakePlaidClient in tests."""
    global _client
    if _client is None:
        _client = PlaidClient()
    return _client
