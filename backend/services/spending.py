import logging
from dataclasses import dataclass

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from models import Transaction

logger = logging.getLogger(__name__)

_effective_category = func.coalesce(
    Transaction.user_category, Transaction.plaid_category, "Uncategorized"
)


@dataclass
class CategorySpend:
    name: str
    amount: float


@dataclass
class SpendingSummary:
    month: str | None
    total: float
    categories: list[CategorySpend]


def spending_by_category(db: Session, month: str | None = None) -> SpendingSummary:
    """Net spend per effective category for a month (or all time), largest first.

    Amounts follow Plaid's sign convention (positive = money out); refunds net
    against their category, so a category's figure is true net outflow."""
    query = db.query(_effective_category, func.sum(Transaction.amount))
    if month:
        year_str, month_str = month.split("-")
        query = query.filter(
            extract("year", Transaction.date) == int(year_str),
            extract("month", Transaction.date) == int(month_str),
        )
    rows = query.group_by(_effective_category).all()

    categories = [CategorySpend(name=name, amount=round(amount, 2)) for name, amount in rows]
    categories.sort(key=lambda c: c.amount, reverse=True)
    total = round(sum(c.amount for c in categories), 2)
    return SpendingSummary(month=month, total=total, categories=categories)
