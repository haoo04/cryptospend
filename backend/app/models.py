from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


class TransactionEvent(Base):
    __tablename__ = "transaction_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", index=True)
    occurred_at: Mapped[str] = mapped_column(String(40), index=True)
    time_precision: Mapped[str] = mapped_column(String(16), default="EXACT")
    description: Mapped[str] = mapped_column(String(500), default="")
    category: Mapped[str | None] = mapped_column(String(100))
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

    __table_args__ = (
        CheckConstraint("status IN ('DRAFT','POSTED','REVERSED')", name="event_status_valid"),
        CheckConstraint("time_precision IN ('EXACT','DATE_ONLY')", name="event_time_precision_valid"),
        Index("ix_events_status_occurred", "status", "occurred_at"),
    )


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
