import json
import logging
from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
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
    # Per-account low-balance alert threshold; null means no low-balance alert.
    low_balance_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)

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
    # Stable key derived from the merchant descriptor; links transactions to rules.
    merchant_key: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    account: Mapped["Account"] = relationship("Account", back_populates="transactions")

    @property
    def effective_category(self) -> str:
        """The user's manual override if set, else Plaid's category, else a sentinel."""
        return self.user_category or self.plaid_category or "Uncategorized"


class MerchantRule(Base):
    """A standing rule: every transaction from this merchant gets this category."""

    __tablename__ = "merchant_rules"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    merchant_key: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String, nullable=False)


class BalanceSnapshot(Base):
    """One account's balance on one day. The daily sync writes these so net worth
    can be charted over time."""

    __tablename__ = "balance_snapshots"
    __table_args__ = (UniqueConstraint("account_id", "date", name="uq_snapshot_account_date"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    balance: Mapped[float] = mapped_column(Float, nullable=False)

    account: Mapped["Account"] = relationship("Account")


class RecurringSeries(Base):
    """A detected recurring charge (subscription or bill), persisted across syncs."""

    __tablename__ = "recurring_series"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    merchant_key: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    cadence: Mapped[str] = mapped_column(String, nullable=False)  # weekly | monthly | annual
    median_amount: Mapped[float] = mapped_column(Float, nullable=False)
    last_seen: Mapped[date] = mapped_column(Date, nullable=False)
    next_expected: Mapped[date] = mapped_column(Date, nullable=False)
    # active: still recurring (recently seen). dismissed: user said "not a subscription".
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    dismissed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Bill(Base):
    """An upcoming obligation shown on the bills calendar.

    A bill is either *derived* — linked to a detected RecurringSeries, with its
    name/amount/cadence/due taken live from that series — or *manual*, where the
    user fills those in for bills detection can't see (rent, annual insurance).
    `due_day_override` pins a monthly bill to a day-of-month regardless of the
    detected/entered date; `autopay` is informational.
    """

    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # Set for derived bills (one bill per series); null for manual bills.
    recurring_series_id: Mapped[int | None] = mapped_column(
        ForeignKey("recurring_series.id"), unique=True, nullable=True, index=True
    )
    # Manual-bill fields; null on derived bills (sourced from the series instead).
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    cadence: Mapped[str | None] = mapped_column(String, nullable=True)
    next_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_day_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    autopay: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    series: Mapped["RecurringSeries | None"] = relationship("RecurringSeries")

    @property
    def is_derived(self) -> bool:
        return self.recurring_series_id is not None

    @property
    def source(self) -> str:
        return "derived" if self.is_derived else "manual"

    @property
    def effective_name(self) -> str:
        if self.series is not None:
            return self.series.merchant_key
        return self.name or "Bill"

    @property
    def effective_amount(self) -> float | None:
        if self.series is not None:
            return self.series.median_amount
        return self.amount

    @property
    def effective_cadence(self) -> str | None:
        if self.series is not None:
            return self.series.cadence
        return self.cadence

    @property
    def base_due(self) -> date | None:
        """The anchor date predictions roll forward from."""
        if self.series is not None:
            return self.series.next_expected
        return self.next_due


class AlertSettings(Base):
    """Singleton (id=1) holding global alert configuration. Per-account low-balance
    thresholds live on Account; this row holds settings with no natural home there."""

    __tablename__ = "alert_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    # A transaction whose absolute amount exceeds this raises an urgent alert; null
    # disables the large-transaction alert entirely.
    large_transaction_amount: Mapped[float | None] = mapped_column(Float, nullable=True)


class AlertEvent(Base):
    """A noteworthy event found during sync. dedupe_key makes recording idempotent;
    urgency decides immediate email vs daily digest. emailed_at is set once sent."""

    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    payload: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    urgency: Mapped[str] = mapped_column(String, nullable=False)  # urgent | digest
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def payload_data(self) -> dict:
        return json.loads(self.payload)
