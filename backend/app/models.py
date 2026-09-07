from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship

from app.database import Base


def new_id() -> str:
    return uuid4().hex


def utc_now_text() -> str:
    return datetime.now(UTC).isoformat()


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    reporting_currency: Mapped[str] = mapped_column(String(16), default="MYR")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kuala_Lumpur")
    cost_method: Mapped[str] = mapped_column(String(32), default="FIFO")
    reconciliation_tolerance_micros: Mapped[int] = mapped_column(Integer, default=10_000)
    updated_at: Mapped[str] = mapped_column(String(40), default=utc_now_text, onupdate=utc_now_text)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(120))
    decimals: Mapped[int] = mapped_column(Integer, default=8)
    chain: Mapped[str | None] = mapped_column(String(64))
    contract_address: Mapped[str | None] = mapped_column(String(160))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now_text)

    __table_args__ = (CheckConstraint("decimals >= 0 AND decimals <= 30", name="asset_decimals_range"),)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    account_type: Mapped[str] = mapped_column(String(32), index=True)
    channel_type: Mapped[str] = mapped_column(String(24), default="OTHER", server_default="OTHER", index=True)
    provider: Mapped[str | None] = mapped_column(String(80))
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now_text)

    entries: Mapped[list[LedgerEntry]] = relationship(back_populates="account")

    __table_args__ = (
        CheckConstraint(
            "account_type IN ('ASSET','LIABILITY','INCOME','EXPENSE','EQUITY','GAIN_LOSS','CLEARING')",
            name="account_type_valid",
        ),
        UniqueConstraint("name", "account_type", "provider", name="uq_account_identity"),
    )


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100))
    normalized_name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(16), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now_text)
    updated_at: Mapped[str] = mapped_column(String(40), default=utc_now_text, onupdate=utc_now_text)

    __table_args__ = (
        CheckConstraint("kind IN ('INCOME','EXPENSE')", name="category_kind_valid"),
        UniqueConstraint("kind", "normalized_name", name="uq_category_kind_name"),
        Index("ix_categories_kind_active_name", "kind", "active", "name"),
    )


class RecurringExpense(Base):
    __tablename__ = "recurring_expenses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    amount_myr: Mapped[int] = mapped_column(Integer)
    frequency: Mapped[str] = mapped_column(String(16))
    anchor_on: Mapped[str] = mapped_column(String(10))
    next_due_on: Mapped[str] = mapped_column(String(10))
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"))
    funding_account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    expense_account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now_text)
    updated_at: Mapped[str] = mapped_column(String(40), default=utc_now_text, onupdate=utc_now_text)

    asset: Mapped[Asset] = relationship()
    funding_account: Mapped[Account] = relationship(foreign_keys=[funding_account_id])
    expense_account: Mapped[Account] = relationship(foreign_keys=[expense_account_id])
    category_ref: Mapped[Category] = relationship()
    occurrences: Mapped[list[RecurringExpenseOccurrence]] = relationship(
        back_populates="recurring_expense", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("amount_myr > 0", name="recurring_expense_amount_positive"),
        CheckConstraint(
            "frequency IN ('WEEKLY','MONTHLY','YEARLY')", name="recurring_expense_frequency_valid"
        ),
        Index("ix_recurring_expenses_active_due", "active", "next_due_on"),
    )


class RecurringExpenseOccurrence(Base):
    __tablename__ = "recurring_expense_occurrences"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    recurring_expense_id: Mapped[str] = mapped_column(ForeignKey("recurring_expenses.id"))
    due_on: Mapped[str] = mapped_column(String(10))
    action: Mapped[str] = mapped_column(String(16))
    scheduled_amount_myr: Mapped[int] = mapped_column(Integer)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("transaction_events.id"), unique=True)
    skip_reason: Mapped[str | None] = mapped_column(String(500))
    handled_at: Mapped[str] = mapped_column(String(40))

    recurring_expense: Mapped[RecurringExpense] = relationship(back_populates="occurrences")
    event: Mapped[TransactionEvent | None] = relationship()

    __table_args__ = (
        UniqueConstraint("recurring_expense_id", "due_on", name="uq_recurring_expense_occurrence_due"),
        CheckConstraint(
            "action IN ('RECORDED','SKIPPED')", name="recurring_expense_occurrence_action_valid"
        ),
        CheckConstraint("scheduled_amount_myr > 0", name="recurring_expense_occurrence_amount_positive"),
        CheckConstraint(
            "((action = 'RECORDED' AND event_id IS NOT NULL AND skip_reason IS NULL) "
            "OR (action = 'SKIPPED' AND event_id IS NULL))",
            name="recurring_expense_occurrence_fields_valid",
        ),
        Index("ix_recurring_expense_occurrences_expense_due", "recurring_expense_id", "due_on"),
    )


class TransactionEvent(Base):
    __tablename__ = "transaction_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", index=True)
    occurred_at: Mapped[str] = mapped_column(String(40), index=True)
    time_precision: Mapped[str] = mapped_column(String(16), default="EXACT")
    description: Mapped[str] = mapped_column(String(500), default="")
    category: Mapped[str | None] = mapped_column(String(100))
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"), index=True)
    source: Mapped[str] = mapped_column(String(40), default="MANUAL")
    external_id: Mapped[str | None] = mapped_column(String(200))
    transaction_value_myr: Mapped[int | None] = mapped_column(Integer)
    reference_value_myr: Mapped[int | None] = mapped_column(Integer)
    reverses_event_id: Mapped[str | None] = mapped_column(ForeignKey("transaction_events.id"), unique=True)
    reversed_by_event_id: Mapped[str | None] = mapped_column(ForeignKey("transaction_events.id"), unique=True)
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now_text)
    posted_at: Mapped[str | None] = mapped_column(String(40))

    entries: Mapped[list[LedgerEntry]] = relationship(
        back_populates="event", cascade="all, delete-orphan", lazy="selectin", foreign_keys="LedgerEntry.event_id"
    )
    fees: Mapped[list[FeeComponent]] = relationship(back_populates="event", lazy="selectin")
    category_ref: Mapped[Category | None] = relationship()
    receipt: Mapped[EventReceipt | None] = relationship(
        back_populates="event", uselist=False, cascade="all, delete-orphan", single_parent=True
    )

    __table_args__ = (
        CheckConstraint("status IN ('DRAFT','POSTED','REVERSED')", name="event_status_valid"),
        CheckConstraint("time_precision IN ('EXACT','DATE_ONLY')", name="event_time_precision_valid"),
        Index("ix_events_status_occurred", "status", "occurred_at"),
    )


class EventReceipt(Base):
    __tablename__ = "event_receipts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("transaction_events.id", ondelete="CASCADE"), unique=True, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(32))
    byte_size: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = deferred(mapped_column(LargeBinary))
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now_text)
    updated_at: Mapped[str] = mapped_column(String(40), default=utc_now_text, onupdate=utc_now_text)

    event: Mapped[TransactionEvent] = relationship(back_populates="receipt")


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("transaction_events.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    direction: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[str] = mapped_column(Text)
    book_amount_myr: Mapped[int] = mapped_column(Integer)
    transaction_value_myr: Mapped[int | None] = mapped_column(Integer)
    reference_value_myr: Mapped[int | None] = mapped_column(Integer)
    valuation_rate: Mapped[str | None] = mapped_column(Text)
    valuation_source: Mapped[str | None] = mapped_column(String(120))

    event: Mapped[TransactionEvent] = relationship(back_populates="entries", foreign_keys=[event_id])
    account: Mapped[Account] = relationship(back_populates="entries")
    asset: Mapped[Asset] = relationship()

    __table_args__ = (
        CheckConstraint("direction IN ('DEBIT','CREDIT')", name="entry_direction_valid"),
        CheckConstraint("book_amount_myr >= 0", name="entry_book_amount_nonnegative"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("transaction_events.id"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    details: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now_text, index=True)


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("transaction_events.id"), unique=True, index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    sell_asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"))
    buy_asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"))
    sell_quantity: Mapped[str] = mapped_column(Text)
    buy_quantity: Mapped[str] = mapped_column(Text)
    execution_rate: Mapped[str] = mapped_column(Text)
    gross_value_myr: Mapped[int] = mapped_column(Integer)
    net_value_myr: Mapped[int] = mapped_column(Integer)
    order_id: Mapped[str | None] = mapped_column(String(200))
    reversed: Mapped[bool] = mapped_column(Boolean, default=False)

    event: Mapped[TransactionEvent] = relationship()
    fills: Mapped[list[TradeFill]] = relationship(back_populates="trade", cascade="all, delete-orphan")


class TradeFill(Base):
    __tablename__ = "trade_fills"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    trade_id: Mapped[str] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), index=True)
    filled_at: Mapped[str] = mapped_column(String(40))
    sell_quantity: Mapped[str] = mapped_column(Text)
    buy_quantity: Mapped[str] = mapped_column(Text)
    price: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(200))

    trade: Mapped[Trade] = relationship(back_populates="fills")


class Transfer(Base):
    __tablename__ = "transfers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("transaction_events.id"), unique=True, index=True)
    source_account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    destination_account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"))
    sent_quantity: Mapped[str] = mapped_column(Text)
    received_quantity: Mapped[str] = mapped_column(Text)
    network: Mapped[str | None] = mapped_column(String(80))
    tx_hash: Mapped[str | None] = mapped_column(String(200), index=True)
    match_status: Mapped[str] = mapped_column(String(32), default="MATCHED")
    reversed: Mapped[bool] = mapped_column(Boolean, default=False)

    event: Mapped[TransactionEvent] = relationship()


class FeeComponent(Base):
    __tablename__ = "fee_components"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("transaction_events.id"), index=True)
    component_type: Mapped[str] = mapped_column(String(64), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"))
    amount: Mapped[str] = mapped_column(Text)
    value_myr: Mapped[int] = mapped_column(Integer)
    source_kind: Mapped[str] = mapped_column(String(16), default="EXPLICIT")
    included_in_funding_amount: Mapped[bool] = mapped_column(Boolean, default=False)
    accounting_treatment: Mapped[str] = mapped_column(String(32), default="EXPENSED")
    calculation_method: Mapped[str | None] = mapped_column(String(160))
    confidence: Mapped[str] = mapped_column(String(32), default="EXACT")
    reversed: Mapped[bool] = mapped_column(Boolean, default=False)

    event: Mapped[TransactionEvent] = relationship(back_populates="fees")
    asset: Mapped[Asset] = relationship()


class RateSnapshot(Base):
    __tablename__ = "rate_snapshots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("transaction_events.id"), index=True)
    base_asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    quote_asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    rate: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[str] = mapped_column(String(40), index=True)
    retrieved_at: Mapped[str] = mapped_column(String(40), default=utc_now_text)
    source: Mapped[str] = mapped_column(String(120))
    rate_type: Mapped[str] = mapped_column(String(32))
    path: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(32), default="EXACT")

    base_asset: Mapped[Asset] = relationship(foreign_keys=[base_asset_id])
    quote_asset: Mapped[Asset] = relationship(foreign_keys=[quote_asset_id])

    __table_args__ = (
        CheckConstraint("base_asset_id <> quote_asset_id", name="rate_assets_differ"),
        Index("ix_rates_pair_observed", "base_asset_id", "quote_asset_id", "observed_at"),
    )


class CostLot(Base):
    __tablename__ = "cost_lots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    source_event_id: Mapped[str] = mapped_column(ForeignKey("transaction_events.id"), index=True)
    parent_lot_id: Mapped[str | None] = mapped_column(ForeignKey("cost_lots.id"))
    acquired_at: Mapped[str] = mapped_column(String(40), index=True)
    original_quantity: Mapped[str] = mapped_column(Text)
    remaining_quantity: Mapped[str] = mapped_column(Text)
    basis_myr: Mapped[int] = mapped_column(Integer)
    remaining_basis_myr: Mapped[int] = mapped_column(Integer)
    basis_status: Mapped[str] = mapped_column(String(24), default="KNOWN")
    voided: Mapped[bool] = mapped_column(Boolean, default=False)

    asset: Mapped[Asset] = relationship()
    account: Mapped[Account] = relationship()

    __table_args__ = (
        CheckConstraint("basis_myr >= 0 AND remaining_basis_myr >= 0", name="lot_basis_nonnegative"),
        CheckConstraint("basis_status IN ('KNOWN','BASIS_UNKNOWN')", name="lot_basis_status_valid"),
        Index("ix_lots_fifo", "account_id", "asset_id", "acquired_at", "id"),
    )


class LotDisposal(Base):
    __tablename__ = "lot_disposals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("transaction_events.id"), index=True)
    cost_lot_id: Mapped[str] = mapped_column(ForeignKey("cost_lots.id"), index=True)
    quantity: Mapped[str] = mapped_column(Text)
    basis_myr: Mapped[int] = mapped_column(Integer)
    proceeds_myr: Mapped[int] = mapped_column(Integer)
    realized_gain_loss_myr: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(String(32), default="DISPOSAL")
    reversed: Mapped[bool] = mapped_column(Boolean, default=False)

    cost_lot: Mapped[CostLot] = relationship()


class LotTransfer(Base):
    __tablename__ = "lot_transfers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("transaction_events.id"), index=True)
    transfer_id: Mapped[str] = mapped_column(ForeignKey("transfers.id"), index=True)
    source_lot_id: Mapped[str] = mapped_column(ForeignKey("cost_lots.id"))
    destination_lot_id: Mapped[str] = mapped_column(ForeignKey("cost_lots.id"))
    quantity: Mapped[str] = mapped_column(Text)
    basis_myr: Mapped[int] = mapped_column(Integer)
    reversed: Mapped[bool] = mapped_column(Boolean, default=False)

    source_lot: Mapped[CostLot] = relationship(foreign_keys=[source_lot_id])
    destination_lot: Mapped[CostLot] = relationship(foreign_keys=[destination_lot_id])


class EventLink(Base):
    __tablename__ = "event_links"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    source_event_id: Mapped[str] = mapped_column(ForeignKey("transaction_events.id"), index=True)
    target_event_id: Mapped[str] = mapped_column(ForeignKey("transaction_events.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(40))

    __table_args__ = (
        UniqueConstraint("source_event_id", "target_event_id", "relation_type", name="uq_event_link"),
        CheckConstraint("source_event_id <> target_event_id", name="event_link_events_differ"),
    )


class CardTransaction(Base):
    __tablename__ = "card_transactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("transaction_events.id"), unique=True, index=True)
    parent_card_transaction_id: Mapped[str | None] = mapped_column(ForeignKey("card_transactions.id"), index=True)
    original_transaction_id: Mapped[str | None] = mapped_column(ForeignKey("card_transactions.id"), index=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    provider_account_id: Mapped[str] = mapped_column(String(160))
    external_id: Mapped[str | None] = mapped_column(String(200))
    transaction_type: Mapped[str] = mapped_column(String(24))
    card_account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    merchant_name: Mapped[str] = mapped_column(String(200))
    merchant_country: Mapped[str | None] = mapped_column(String(2))
    merchant_asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"))
    merchant_amount: Mapped[str] = mapped_column(Text)
    billing_asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"))
    billing_amount: Mapped[str] = mapped_column(Text)
    merchant_value_myr: Mapped[int] = mapped_column(Integer)
    funding_value_myr: Mapped[int] = mapped_column(Integer, default=0)
    separate_fee_value_myr: Mapped[int] = mapped_column(Integer, default=0)
    gross_economic_cost_myr: Mapped[int] = mapped_column(Integer, default=0)
    net_economic_cost_myr: Mapped[int] = mapped_column(Integer, default=0)
    total_leakage_myr: Mapped[int] = mapped_column(Integer, default=0)
    actual_fx_rate: Mapped[str | None] = mapped_column(Text)
    reference_fx_rate: Mapped[str | None] = mapped_column(Text)
    fx_deviation_myr: Mapped[int | None] = mapped_column(Integer)
    conversion_deviation_myr: Mapped[int | None] = mapped_column(Integer)
    residual_myr: Mapped[int | None] = mapped_column(Integer)
    breakdown_confidence: Mapped[str] = mapped_column(String(32), default="MISSING_INPUT")
    status: Mapped[str] = mapped_column(String(32), index=True)
    authorized_at: Mapped[str | None] = mapped_column(String(40))
    settled_at: Mapped[str | None] = mapped_column(String(40), index=True)
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now_text)
    reversed: Mapped[bool] = mapped_column(Boolean, default=False)

    event: Mapped[TransactionEvent | None] = relationship()
    funding_legs: Mapped[list[CardFundingLeg]] = relationship(back_populates="card_transaction", lazy="selectin")
    cost_components: Mapped[list[CardCostComponent]] = relationship(
        back_populates="card_transaction", lazy="selectin"
    )
    rewards: Mapped[list[Reward]] = relationship(back_populates="card_transaction", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("provider", "provider_account_id", "external_id", name="uq_card_external_record"),
        CheckConstraint(
            "status IN ('AUTHORIZED','SETTLED','PARTIALLY_SETTLED','REVERSED','PARTIALLY_REFUNDED','REFUNDED')",
            name="card_status_valid",
        ),
        CheckConstraint("transaction_type IN ('AUTHORIZATION','PURCHASE','REFUND')", name="card_type_valid"),
    )


class CardHold(Base):
    __tablename__ = "card_holds"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    card_transaction_id: Mapped[str] = mapped_column(ForeignKey("card_transactions.id"), unique=True, index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"))
    amount: Mapped[str] = mapped_column(Text)
    value_myr: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now_text)
    released_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (CheckConstraint("status IN ('ACTIVE','RELEASED')", name="card_hold_status_valid"),)


class CardFundingLeg(Base):
    __tablename__ = "card_funding_legs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    card_transaction_id: Mapped[str] = mapped_column(ForeignKey("card_transactions.id"), index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("transaction_events.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"))
    quantity: Mapped[str] = mapped_column(Text)
    transaction_value_myr: Mapped[int] = mapped_column(Integer)
    reference_value_myr: Mapped[int] = mapped_column(Integer)
    book_basis_myr: Mapped[int] = mapped_column(Integer)
    actual_conversion_rate: Mapped[str | None] = mapped_column(Text)
    leg_type: Mapped[str] = mapped_column(String(16), default="FUNDING")
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    reversed: Mapped[bool] = mapped_column(Boolean, default=False)

    card_transaction: Mapped[CardTransaction] = relationship(back_populates="funding_legs")
    asset: Mapped[Asset] = relationship()
    account: Mapped[Account] = relationship()

    __table_args__ = (CheckConstraint("leg_type IN ('FUNDING','REFUND')", name="card_leg_type_valid"),)


class CardCostComponent(Base):
    __tablename__ = "card_cost_components"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    card_transaction_id: Mapped[str] = mapped_column(ForeignKey("card_transactions.id"), index=True)
    component_type: Mapped[str] = mapped_column(String(48))
    value_myr: Mapped[int] = mapped_column(Integer)
    source_kind: Mapped[str] = mapped_column(String(16), default="DERIVED")
    calculation_method: Mapped[str] = mapped_column(String(240))
    confidence: Mapped[str] = mapped_column(String(32))

    card_transaction: Mapped[CardTransaction] = relationship(back_populates="cost_components")


class Reward(Base):
    __tablename__ = "rewards"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    card_transaction_id: Mapped[str] = mapped_column(ForeignKey("card_transactions.id"), index=True)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("transaction_events.id"), unique=True, index=True)
    reward_type: Mapped[str] = mapped_column(String(48))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"))
    amount: Mapped[str] = mapped_column(Text)
    value_myr: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), index=True)
    earned_at: Mapped[str] = mapped_column(String(40))
    credited_at: Mapped[str | None] = mapped_column(String(40))
    reversed_at: Mapped[str | None] = mapped_column(String(40))
    external_id: Mapped[str | None] = mapped_column(String(200))

    card_transaction: Mapped[CardTransaction] = relationship(back_populates="rewards")
    asset: Mapped[Asset] = relationship()
    account: Mapped[Account] = relationship()

    __table_args__ = (
        CheckConstraint("status IN ('PENDING','CREDITED','REVERSED','EXPIRED')", name="reward_status_valid"),
    )


class Journey(Base):
    __tablename__ = "journeys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    journey_type: Mapped[str] = mapped_column(String(24), index=True)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", index=True)
    allocation_method: Mapped[str] = mapped_column(String(160))
    confidence: Mapped[str] = mapped_column(String(32))
    notes: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now_text)

    event_links: Mapped[list[JourneyEventLink]] = relationship(
        back_populates="journey", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("journey_type IN ('FUNDS','PAYMENT','WITHDRAWAL')", name="journey_type_valid"),
        CheckConstraint("status IN ('DRAFT','CONFIRMED','COMPLETED')", name="journey_status_valid"),
        CheckConstraint(
            "confidence IN ('EXACT','HIGH','ESTIMATED','MISSING_INPUT')", name="journey_confidence_valid"
        ),
    )


class JourneyEventLink(Base):
    __tablename__ = "journey_event_links"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    journey_id: Mapped[str] = mapped_column(ForeignKey("journeys.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("transaction_events.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(40), default="STEP")
    sequence: Mapped[int] = mapped_column(Integer, default=0)

    journey: Mapped[Journey] = relationship(back_populates="event_links")
    event: Mapped[TransactionEvent] = relationship()
    allocations: Mapped[list[JourneyAllocation]] = relationship(
        back_populates="event_link", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (UniqueConstraint("journey_id", "event_id", name="uq_journey_event"),)


class JourneyAllocation(Base):
    __tablename__ = "journey_allocations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    event_link_id: Mapped[str] = mapped_column(ForeignKey("journey_event_links.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    allocation_role: Mapped[str] = mapped_column(String(24))
    quantity: Mapped[str] = mapped_column(Text)
    value_myr: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(160))
    confidence: Mapped[str] = mapped_column(String(32))

    event_link: Mapped[JourneyEventLink] = relationship(back_populates="allocations")
    asset: Mapped[Asset] = relationship()

    __table_args__ = (
        CheckConstraint(
            "allocation_role IN ('INPUT','INTERMEDIATE','OUTPUT','COST')", name="journey_allocation_role_valid"
        ),
        CheckConstraint("value_myr >= 0", name="journey_allocation_value_nonnegative"),
        CheckConstraint(
            "confidence IN ('EXACT','HIGH','ESTIMATED','MISSING_INPUT')",
            name="journey_allocation_confidence_valid",
        ),
    )


class ReportSnapshot(Base):
    __tablename__ = "report_snapshots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    snapshot_type: Mapped[str] = mapped_column(String(24), index=True)
    period_key: Mapped[str] = mapped_column(String(16), index=True)
    period_start: Mapped[str] = mapped_column(String(40))
    as_of: Mapped[str] = mapped_column(String(40), index=True)
    timezone: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now_text)

    __table_args__ = (
        CheckConstraint("snapshot_type IN ('MONTHLY')", name="report_snapshot_type_valid"),
    )
