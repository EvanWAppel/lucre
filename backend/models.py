import logging
from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

logger = logging.getLogger(__name__)


class Item(Base):
    """One row per connected Plaid institution."""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    plaid_item_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    # Access token is stored encrypted at rest
    encrypted_access_token: Mapped[str] = mapped_column(String, nullable=False)
    institution_name: Mapped[str] = mapped_column(String, nullable=False)
    # Cursor for Plaid /transactions/sync; null until the first transactions sync.
    sync_cursor: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    accounts: Mapped[list["Account"]] = relationship(
        "Account", back_populates="item", cascade="all, delete-orphan"
    )


class Account(Base):
    """One row per account at a connected institution."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False, index=True)
    plaid_account_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    account_type: Mapped[str] = mapped_column(String, nullable=False)  # depository | credit
    subtype: Mapped[str | None] = mapped_column(String, nullable=True)
    balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    item: Mapped["Item"] = relationship("Item", back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="account", cascade="all, delete-orphan"
    )

    def touch(self, balance: float | None) -> None:
        self.balance = balance
        self.last_refreshed_at = datetime.now(UTC)


class Transaction(Base):
    """One row per Plaid transaction. amount follows Plaid's sign convention:
    positive = money out, negative = money in (refunds, deposits)."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    plaid_transaction_id: Mapped[str] = mapped_column(
        String, unique=True, nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    merchant_name: Mapped[str | None] = mapped_column(String, nullable=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    plaid_category: Mapped[str | None] = mapped_column(String, nullable=True)
    user_category: Mapped[str | None] = mapped_column(String, nullable=True)
    pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    account: Mapped["Account"] = relationship("Account", back_populates="transactions")

    @property
    def effective_category(self) -> str:
        """The user's manual override if set, else Plaid's category, else a sentinel."""
        return self.user_category or self.plaid_category or "Uncategorized"
