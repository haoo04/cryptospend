from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator

from app.enums import AccountType, EntryDirection, EventType
from app.money import canonical_decimal, parse_decimal


class AssetCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=120)
    decimals: int = Field(default=8, ge=0, le=30)
    chain: str | None = Field(default=None, max_length=64)
    contract_address: str | None = Field(default=None, max_length=160)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    account_type: AccountType
    provider: str | None = Field(default=None, max_length=80)


class OnboardingCreate(BaseModel):
    reporting_currency: str = "MYR"
    timezone: str = "Asia/Kuala_Lumpur"
    accounts: list[AccountCreate] = Field(default_factory=list)


class EntryCreate(BaseModel):
    account_id: str
    asset_id: str
    direction: EntryDirection
    quantity: str
    book_amount_myr: str
    transaction_value_myr: str | None = None
    reference_value_myr: str | None = None
    valuation_rate: str | None = None
    valuation_source: str | None = Field(default=None, max_length=120)

    @field_validator("quantity", "book_amount_myr", "transaction_value_myr", "reference_value_myr", "valuation_rate")
    @classmethod
    def validate_decimal(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = canonical_decimal(value)
        if parse_decimal(normalized) < 0:
            raise ValueError("amounts must be non-negative")
        return normalized


class EventDraftCreate(BaseModel):
    event_type: EventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    time_precision: str = Field(default="EXACT", pattern="^(EXACT|DATE_ONLY)$")
    description: str = Field(default="", max_length=500)
    category: str | None = Field(default=None, max_length=100)
    source: str = Field(default="MANUAL", max_length=40)
    external_id: str | None = Field(default=None, max_length=200)
    transaction_value_myr: str | None = None
    reference_value_myr: str | None = None
    entries: list[EntryCreate] = Field(min_length=1)

    @field_validator("transaction_value_myr", "reference_value_myr")
    @classmethod
    def validate_event_value(cls, value: str | None) -> str | None:
        return canonical_decimal(value) if value is not None else None


class ManualEventCreate(BaseModel):
    event_type: EventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    description: str = Field(default="", max_length=500)
    category: str | None = Field(default=None, max_length=100)
    debit_account_id: str
    credit_account_id: str
    asset_id: str
    quantity: str
    book_amount_myr: str
    valuation_rate: str | None = None
    valuation_source: str | None = Field(default=None, max_length=120)

    @field_validator("quantity", "book_amount_myr", "valuation_rate")
    @classmethod
    def validate_decimal(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = canonical_decimal(value)
        if parse_decimal(normalized) < 0:
            raise ValueError("amounts must be non-negative")
        return normalized


class ReverseCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class AssetRead(BaseModel):
    id: str
    symbol: str
    name: str
    decimals: int
    chain: str | None
    contract_address: str | None
    active: bool


class BalanceRead(BaseModel):
    asset_id: str
    asset_symbol: str
    quantity: str
    book_amount_myr: str


class AccountRead(BaseModel):
    id: str
    name: str
    account_type: str
    provider: str | None
    closed: bool
    balances: list[BalanceRead] = Field(default_factory=list)


class EntryRead(BaseModel):
    id: str
    account_id: str
    account_name: str
    asset_id: str
    asset_symbol: str
    direction: str
    quantity: str
    book_amount_myr: str
    transaction_value_myr: str | None
    reference_value_myr: str | None
    valuation_rate: str | None
    valuation_source: str | None


class EventRead(BaseModel):
    id: str
    event_type: str
    status: str
    occurred_at: str
    time_precision: str
    description: str
    category: str | None
    source: str
    external_id: str | None
    transaction_value_myr: str | None
    reference_value_myr: str | None
    reverses_event_id: str | None
    reversed_by_event_id: str | None
    posted_at: str | None
    entries: list[EntryRead]


class SettingsRead(BaseModel):
    reporting_currency: str
    timezone: str
    cost_method: str


class SummaryRead(BaseModel):
    net_worth_myr: str
    income_myr: str
    expense_myr: str
    gross_spending_myr: str
    net_spending_myr: str
