import logging

from sqlalchemy.orm import Session

from models import MerchantRule, Transaction
from services.merchants import merchant_key

logger = logging.getLogger(__name__)


def load_rules(db: Session) -> dict[str, str]:
    """All merchant rules as a {merchant_key: category} map, for sync-time lookup."""
    return {rule.merchant_key: rule.category for rule in db.query(MerchantRule).all()}


def upsert_rule(db: Session, key: str, category: str) -> MerchantRule:
    """Create or update the rule for a merchant key."""
    rule = db.query(MerchantRule).filter_by(merchant_key=key).first()
    if rule is None:
        rule = MerchantRule(merchant_key=key, category=category)
        db.add(rule)
    else:
        rule.category = category
    db.commit()
    logger.info("Merchant rule: %s -> %s", key, category)
    return rule


def delete_rule(db: Session, key: str) -> None:
    db.query(MerchantRule).filter_by(merchant_key=key).delete()
    db.commit()


def apply_rule_to_existing(db: Session, key: str, category: str) -> int:
    """Retroactively set user_category on every existing transaction whose merchant
    normalizes to `key`. Computes the key on the fly so it works even before
    merchant_key has been backfilled. Returns the number of transactions updated."""
    count = 0
    for txn in db.query(Transaction).all():
        if merchant_key(txn.merchant_name or txn.name) == key:
            txn.user_category = category
            txn.merchant_key = key
            count += 1
    db.commit()
    logger.info("Applied rule %s -> %s to %d existing transactions", key, category, count)
    return count
