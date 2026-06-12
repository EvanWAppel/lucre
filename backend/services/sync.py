import logging

from sqlalchemy.orm import Session

from crypto import decrypt
from models import Account, Item
from plaid_client import PlaidClientLike

logger = logging.getLogger(__name__)


def sync_balances(db: Session, plaid: PlaidClientLike) -> dict:
    """Refresh balances for every connected item. One failing item is logged and
    reported in the result, but never aborts the rest."""
    items = db.query(Item).all()
    items_synced = 0
    accounts_updated = 0
    errors: list[str] = []

    for item in items:
        try:
            raw_accounts = plaid.get_accounts(decrypt(item.encrypted_access_token))
        except Exception:
            logger.exception("Sync failed for %s", item.institution_name)
            errors.append(item.institution_name)
            continue

        existing = {account.plaid_account_id: account for account in item.accounts}
        for raw in raw_accounts:
            account = existing.get(raw["plaid_account_id"])
            if account is None:
                account = Account(
                    item_id=item.id,
                    plaid_account_id=raw["plaid_account_id"],
                    name=raw["name"],
                    account_type=raw["type"],
                    subtype=raw["subtype"],
                )
                db.add(account)
            else:
                account.name = raw["name"]
            account.touch(raw["balance"])
            accounts_updated += 1
        items_synced += 1

    db.commit()
    logger.info(
        "Balance sync: %d items, %d accounts, %d errors",
        items_synced,
        accounts_updated,
        len(errors),
    )
    return {"items_synced": items_synced, "accounts_updated": accounts_updated, "errors": errors}
