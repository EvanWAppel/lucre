import logging
from datetime import date

from sqlalchemy.orm import Session

from crypto import decrypt
from models import Account, Item, Transaction
from plaid_client import PlaidClientLike
from services.merchants import merchant_key
from services.rules import load_rules

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


def _upsert_transaction(db: Session, account_id: int, raw: dict, rules: dict[str, str]) -> bool:
    """Insert a new transaction or update mutable fields of an existing one.
    Returns True if newly inserted. The user's manual category override is never
    touched; a matching merchant rule only auto-categorizes brand-new transactions."""
    txn = db.query(Transaction).filter_by(plaid_transaction_id=raw["plaid_transaction_id"]).first()
    is_new = txn is None
    if is_new:
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
    txn.merchant_key = merchant_key(raw["merchant_name"] or raw["name"])
    if is_new and txn.merchant_key and txn.merchant_key in rules:
        txn.user_category = rules[txn.merchant_key]
    return is_new


def sync_transactions(db: Session, plaid: PlaidClientLike) -> dict:
    """Pull transactions for every item via Plaid's cursor-based /transactions/sync.

    Pages are applied and the cursor saved after each page, so an interrupted sync
    resumes from where it stopped. One failing item is logged and reported, never
    aborting the rest."""
    items = db.query(Item).all()
    rules = load_rules(db)
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
                    if _upsert_transaction(db, account_id, raw, rules):
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


def run_full_sync(db: Session, plaid: PlaidClientLike, today: date) -> dict:
    """The daily pipeline: refresh balances, ingest transactions, then re-detect
    recurring series (which raises new-subscription and price-increase alerts)."""
    # Imported here to avoid a module-load cycle (subscriptions imports nothing from
    # sync, but keeping the edge lazy documents the run-order dependency).
    from services.subscriptions import sync_recurring

    balances = sync_balances(db, plaid)
    transactions = sync_transactions(db, plaid)
    recurring = sync_recurring(db, today)
    logger.info("Full sync complete")
    return {"balances": balances, "transactions": transactions, "recurring": recurring}
