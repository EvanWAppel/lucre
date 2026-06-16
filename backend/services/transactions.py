import logging
from dataclasses import dataclass

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from models import Transaction

logger = logging.getLogger(__name__)

PER_PAGE = 50
UNCATEGORIZED = "Uncategorized"

# COALESCE(user_category, plaid_category): the effective category as a SQL expression
# so it can be filtered/grouped in the database (mirrors Transaction.effective_category).
_effective_category = func.coalesce(Transaction.user_category, Transaction.plaid_category)


@dataclass
class TransactionPage:
    transactions: list[Transaction]
    page: int
    has_next: bool


def _apply_filters(query, month: str | None, account_id: int | None, category: str | None):
    if month:
        year_str, month_str = month.split("-")
        query = query.filter(
            extract("year", Transaction.date) == int(year_str),
            extract("month", Transaction.date) == int(month_str),
        )
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)
    if category == UNCATEGORIZED:
        query = query.filter(_effective_category.is_(None))
    elif category:
        query = query.filter(_effective_category == category)
    return query


def distinct_categories(db: Session) -> list[str]:
    """All effective categories present in the data, for the filter dropdown."""
    rows = db.query(_effective_category).distinct().all()
    cats = sorted(r[0] for r in rows if r[0] is not None)
    if db.query(Transaction).filter(_effective_category.is_(None)).first() is not None:
        cats.append(UNCATEGORIZED)
    return cats


def query_transactions(
    db: Session,
    month: str | None = None,
    account_id: int | None = None,
    category: str | None = None,
    page: int = 1,
) -> TransactionPage:
    """Filtered, paginated transactions, most recent first."""
    query = _apply_filters(db.query(Transaction), month, account_id, category)
    query = query.order_by(Transaction.date.desc(), Transaction.id.desc())

    # Fetch one extra row to tell whether a next page exists without a count query.
    rows = query.offset((page - 1) * PER_PAGE).limit(PER_PAGE + 1).all()
    has_next = len(rows) > PER_PAGE
    return TransactionPage(transactions=rows[:PER_PAGE], page=page, has_next=has_next)
