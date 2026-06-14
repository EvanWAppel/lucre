import logging

from sqlalchemy.orm import Session

from crypto import decrypt
from models import Account, Item, Transaction
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


def _upsert_transaction(db: Session, account_id: int, raw: dict) -> None:
    """Insert a new transaction or update mutable fields of an existing one.
    The user's manual category override is never touched."""
    txn = db.query(Transaction).filter_by(plaid_transaction_id=raw["plaid_transaction_id"]).first()
    if txn is None:
        txn = Transaction(
            account_id=account_id,
            plaid_transaction_id=raw["plaid_transaction_id"],
        )
        db.add(txn)
    txn.date = raw["date"]
    txn.name = raw["name"]
    txn.merchant_name = raw["merchant_name"]
    txn.amount = raw["amount"]
    txn.plaid_category = raw["plaid_category"]
    txn.pending = raw["pending"]


def sync_transactions(db: Session, plaid: PlaidClientLike) -> dict:
    """Pull transactions for every item via Plaid's cursor-based /transactions/sync.

    Pages are applied and the cursor saved after each page, so an interrupted sync
    resumes from where it stopped. One failing item is logged and reported, never
    aborting the rest."""
    items = db.query(Item).all()
    added = modified = removed = 0
    errors: list[str] = []

    for item in items:
        try:
            access_token = decrypt(item.encrypted_access_token)
            account_ids = {a.plaid_account_id: a.id for a in item.accounts}
            cursor = item.sync_cursor
            while True:
                page = plaid.transactions_sync(access_token, cursor)
                for raw in page["added"] + page["modified"]:
                    account_id = account_ids.get(raw["plaid_account_id"])
                    if account_id is None:
                        logger.warning(
                            "Transaction %s references unknown account %s; skipping",
                            raw["plaid_transaction_id"],
                            raw["plaid_account_id"],
                        )
                        continue
                    is_new = (
                        db.query(Transaction.id)
                        .filter_by(plaid_transaction_id=raw["plaid_transaction_id"])
                        .first()
                        is None
                    )
                    _upsert_transaction(db, account_id, raw)
                    if is_new:
                        added += 1
                    else:
                        modified += 1
                for plaid_transaction_id in page["removed"]:
                    deleted = (
                        db.query(Transaction)
                        .filter_by(plaid_transaction_id=plaid_transaction_id)
                        .delete()
                    )
                    removed += deleted
                cursor = page["next_cursor"]
                item.sync_cursor = cursor
                db.commit()
                if not page["has_more"]:
                    break
        except Exception:
            logger.exception("Transaction sync failed for %s", item.institution_name)
            db.rollback()
            errors.append(item.institution_name)
            continue

    logger.info(
        "Transaction sync: +%d added, ~%d modified, -%d removed, %d errors",
        added,
        modified,
        removed,
        len(errors),
    )
    return {"added": added, "modified": modified, "removed": removed, "errors": errors}
