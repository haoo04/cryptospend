from datetime import UTC, date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.enums import (
    AccountChannel,
    AccountType,
    CategoryKind,
    EntryDirection,
    EventType,
    FeeTreatment,
    RecurringFrequency,
    RecurringOccurrenceAction,
)
from app.money import canonical_decimal, parse_decimal

MANUAL_EVENT_TYPES = {
    EventType.OPENING_BALANCE,
    EventType.SALARY,
    EventType.INCOME,
    EventType.EXPENSE,
    EventType.ADJUSTMENT,
}


def clean_category_name(value: str) -> str:
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        raise ValueError("category name must not be blank")
    return cleaned


def normalize_category_name(value: str) -> str:
    return clean_category_name(value).casefold()


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: CategoryKind

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return clean_category_name(value)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    active: bool | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return clean_category_name(value) if value is not None else None

    @model_validator(mode="after")
    def require_change(self) -> "CategoryUpdate":
        if self.name is None and self.active is None:
            raise ValueError("at least one category field must be provided")
        return self


class CategoryRead(BaseModel):
    id: str
    name: str
    kind: str
    active: bool
    created_at: str
    updated_at: str


class EventCategoryUpdate(BaseModel):
    category_id: str = Field(min_length=1)


def clean_recurring_expense_name(value: str) -> str:
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        raise ValueError("recurring expense name must not be blank")
    return cleaned


class RecurringExpenseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    amount_myr: str = Field(min_length=1)
    frequency: RecurringFrequency
    first_due_on: date
    asset_id: str = Field(min_length=1)
    funding_account_id: str = Field(min_length=1)
    expense_account_id: str = Field(min_length=1)
    category_id: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return clean_recurring_expense_name(value)

    @field_validator("amount_myr")
    @classmethod
    def validate_amount(cls, value: str) -> str:
        normalized = canonical_decimal(value)
        if parse_decimal(normalized) <= 0:
            raise ValueError("amount_myr must be greater than zero")
        return normalized


class RecurringExpenseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    amount_myr: str | None = Field(default=None, min_length=1)
    frequency: RecurringFrequency | None = None
    next_due_on: date | None = None
    asset_id: str | None = Field(default=None, min_length=1)
    funding_account_id: str | None = Field(default=None, min_length=1)
    expense_account_id: str | None = Field(default=None, min_length=1)
    category_id: str | None = Field(default=None, min_length=1)
    active: bool | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return clean_recurring_expense_name(value) if value is not None else None

    @field_validator("amount_myr")
    @classmethod
    def validate_amount(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = canonical_decimal(value)
        if parse_decimal(normalized) <= 0:
            raise ValueError("amount_myr must be greater than zero")
        return normalized

    @model_validator(mode="after")
    def require_change_and_schedule_pair(self) -> "RecurringExpenseUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one recurring expense field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("recurring expense fields must not be null")
        has_frequency = "frequency" in self.model_fields_set
        has_next_due = "next_due_on" in self.model_fields_set
        if has_frequency != has_next_due:
            raise ValueError("frequency and next_due_on must be provided together when resetting the schedule")
        return self


class RecurringExpenseRecordCreate(BaseModel):
    due_on: date
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RecurringExpenseSkipCreate(BaseModel):
    due_on: date
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class RecurringExpenseSummaryRead(BaseModel):
    active_count: int
    overdue_count: int
    weekly_total_myr: str
    monthly_total_myr: str
    yearly_total_myr: str
    annualized_myr: str


class RecurringExpenseRead(BaseModel):
    id: str
    name: str
    amount_myr: str
    frequency: str
    anchor_on: str
    next_due_on: str
    due_status: str
    annualized_amount_myr: str
    asset_id: str
    funding_account_id: str
    expense_account_id: str
    category_id: str
    active: bool
    created_at: str
    updated_at: str


class RecurringExpenseListRead(BaseModel):
    as_of: str
    timezone: str
    summary: RecurringExpenseSummaryRead
    items: list[RecurringExpenseRead]


class RecurringExpenseOccurrenceRead(BaseModel):
    id: str
    recurring_expense_id: str
    due_on: str
    action: RecurringOccurrenceAction
    scheduled_amount_myr: str
    event_id: str | None
    event_status: str | None
    occurred_at: str | None
    skip_reason: str | None
    handled_at: str


class RecurringExpenseActionRead(BaseModel):
    occurrence: RecurringExpenseOccurrenceRead
    recurring_expense: RecurringExpenseRead


class ReceiptRead(BaseModel):
    id: str
    original_filename: str
    content_type: str
    byte_size: int
    created_at: str
    updated_at: str


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
    channel_type: AccountChannel = AccountChannel.OTHER
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
    category_id: str | None = None
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
    category_id: str | None = None
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
        if parse_decimal(normalized) <= 0:
            raise ValueError("amounts must be positive")
        return normalized

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: EventType) -> EventType:
        if value not in MANUAL_EVENT_TYPES:
            raise ValueError("manual event type must use a dedicated workflow")
        return value


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
    channel_type: str
    provider: str | None
    closed: bool
    balances: list[BalanceRead] = Field(default_factory=list)
    available_balances: list[BalanceRead] = Field(default_factory=list)


class AccountLedgerCounterpartyRead(BaseModel):
    account_id: str
    account_name: str
    account_type: str


class AccountLedgerItemRead(BaseModel):
    event_id: str
    event_type: str
    event_status: str
    occurred_at: str
    time_precision: str
    description: str
    category: str | None
    source: str
    reverses_event_id: str | None
    reversed_by_event_id: str | None
    asset_id: str
    asset_symbol: str
    quantity_change: str
    book_amount_myr_change: str
    balance_after_quantity: str
    balance_after_book_amount_myr: str
    entry_count: int
    counterparties: list[AccountLedgerCounterpartyRead] = Field(default_factory=list)
    receipt_attached: bool


class AccountLedgerPageRead(BaseModel):
    account: AccountRead
    timezone: str
    items: list[AccountLedgerItemRead]
    total: int
    page: int
    page_size: int


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
    category_id: str | None
    category_kind: str | None
    source: str
    external_id: str | None
    transaction_value_myr: str | None
    reference_value_myr: str | None
    reverses_event_id: str | None
    reversed_by_event_id: str | None
    posted_at: str | None
    entries: list[EntryRead]
    fees: list["FeeRead"] = Field(default_factory=list)
    receipt: ReceiptRead | None = None


class EventSearchPageRead(BaseModel):
    items: list[EventRead]
    total: int
    page: int
    page_size: int


class SettingsRead(BaseModel):
    reporting_currency: str
    timezone: str
    cost_method: str


class GoogleDriveBackupStatusRead(BaseModel):
    configured: bool
    supported: bool
    connected: bool
    folder_name: str
    message: str | None = None


class GoogleDriveBackupRead(BaseModel):
    id: str
    name: str
    web_view_link: str | None
    created_at: str


class SummaryRead(BaseModel):
    net_worth_myr: str
    income_myr: str
    expense_myr: str
    gross_spending_myr: str
    net_spending_myr: str


class FeeCreate(BaseModel):
    component_type: str = Field(min_length=1, max_length=64)
    asset_id: str
    amount: str
    value_myr: str
    accounting_treatment: FeeTreatment = FeeTreatment.EXPENSED
    included_in_funding_amount: bool = False
    expense_account_id: str | None = None
    funding_account_id: str | None = None
    calculation_method: str | None = Field(default=None, max_length=160)

    @field_validator("amount", "value_myr")
    @classmethod
    def validate_amount(cls, value: str) -> str:
        normalized = canonical_decimal(value)
        if parse_decimal(normalized) < 0:
            raise ValueError("amounts must be non-negative")
        return normalized


class FeeRead(BaseModel):
    id: str
    component_type: str
    asset_id: str
    asset_symbol: str
    amount: str
    value_myr: str
    source_kind: str
    included_in_funding_amount: bool
    accounting_treatment: str
    calculation_method: str | None
    confidence: str


class TradeCreate(BaseModel):
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    account_id: str
    sell_asset_id: str
    sell_quantity: str
    buy_asset_id: str
    buy_quantity: str
    execution_rate: str
    gross_value_myr: str
    order_id: str | None = Field(default=None, max_length=200)
    description: str = Field(default="", max_length=500)
    gain_loss_account_id: str
    fee: FeeCreate | None = None

    @field_validator("sell_quantity", "buy_quantity", "execution_rate", "gross_value_myr")
    @classmethod
    def validate_trade_decimal(cls, value: str) -> str:
        normalized = canonical_decimal(value)
        if parse_decimal(normalized) <= 0:
            raise ValueError("trade values must be positive")
        return normalized


class TransferCreate(BaseModel):
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_account_id: str
    destination_account_id: str
    asset_id: str
    sent_quantity: str
    received_quantity: str
    network: str | None = Field(default=None, max_length=80)
    tx_hash: str | None = Field(default=None, max_length=200)
    description: str = Field(default="", max_length=500)
    gain_loss_account_id: str
    fee: FeeCreate | None = None

    @field_validator("sent_quantity", "received_quantity")
    @classmethod
    def validate_transfer_decimal(cls, value: str) -> str:
        normalized = canonical_decimal(value)
        if parse_decimal(normalized) <= 0:
            raise ValueError("transfer quantities must be positive")
        return normalized


class RateCreate(BaseModel):
    base_asset_id: str
    quote_asset_id: str
    rate: str
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str = Field(min_length=1, max_length=120)
    rate_type: str = Field(default="MARKET", max_length=32)
    path: str | None = None
    confidence: str = Field(default="EXACT", pattern="^(EXACT|HIGH|ESTIMATED|MISSING_INPUT)$")

    @field_validator("rate")
    @classmethod
    def validate_rate(cls, value: str) -> str:
        normalized = canonical_decimal(value)
        if parse_decimal(normalized) <= 0:
            raise ValueError("rate must be positive")
        return normalized


class CostLotRead(BaseModel):
    id: str
    asset_id: str
    asset_symbol: str
    account_id: str
    account_name: str
    source_event_id: str
    acquired_at: str
    original_quantity: str
    remaining_quantity: str
    basis_myr: str
    remaining_basis_myr: str
    basis_status: str
    voided: bool


class PortfolioPositionRead(BaseModel):
    asset_id: str
    symbol: str
    quantity: str
    cost_basis_myr: str
    average_cost_myr: str | None
    market_rate_myr: str | None
    market_rate_source: str | None
    market_rate_observed_at: str | None
    market_rate_confidence: str | None
    market_value_myr: str | None
    unrealized_gain_loss_myr: str | None
    realized_gain_loss_myr: str
    basis_complete: bool


class CardAuthorizationCreate(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    provider_account_id: str = Field(min_length=1, max_length=160)
    external_id: str | None = Field(default=None, max_length=200)
    card_account_id: str
    merchant_name: str = Field(min_length=1, max_length=200)
    merchant_country: str | None = Field(default=None, min_length=2, max_length=2)
    merchant_asset_id: str
    merchant_amount: str
    billing_asset_id: str
    billing_amount: str
    merchant_value_myr: str
    hold_account_id: str
    hold_asset_id: str
    hold_amount: str
    hold_value_myr: str
    authorized_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("merchant_amount", "billing_amount", "merchant_value_myr", "hold_amount", "hold_value_myr")
    @classmethod
    def validate_authorization_decimal(cls, value: str) -> str:
        normalized = canonical_decimal(value)
        if parse_decimal(normalized) <= 0:
            raise ValueError("authorization amounts must be positive")
        return normalized


class CardFundingLegCreate(BaseModel):
    account_id: str
    asset_id: str
    quantity: str
    transaction_value_myr: str
    reference_value_myr: str
    actual_conversion_rate: str | None = None

    @field_validator("quantity", "transaction_value_myr", "reference_value_myr", "actual_conversion_rate")
    @classmethod
    def validate_funding_decimal(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = canonical_decimal(value)
        if parse_decimal(normalized) <= 0:
            raise ValueError("funding values must be positive")
        return normalized


class CardSettlementCreate(BaseModel):
    authorization_id: str | None = None
    provider: str = Field(min_length=1, max_length=80)
    provider_account_id: str = Field(min_length=1, max_length=160)
    external_id: str | None = Field(default=None, max_length=200)
    card_account_id: str
    merchant_name: str = Field(min_length=1, max_length=200)
    merchant_country: str | None = Field(default=None, min_length=2, max_length=2)
    merchant_asset_id: str
    merchant_amount: str
    billing_asset_id: str
    billing_amount: str
    merchant_value_myr: str
    reference_fx_rate: str | None = None
    expense_account_id: str
    category_id: str | None = None
    gain_loss_account_id: str
    funding_legs: list[CardFundingLegCreate] = Field(min_length=1)
    fees: list[FeeCreate] = Field(default_factory=list)
    settled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    final_capture: bool = True
    description: str = Field(default="", max_length=500)

    @field_validator("merchant_amount", "billing_amount", "merchant_value_myr", "reference_fx_rate")
    @classmethod
    def validate_settlement_decimal(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = canonical_decimal(value)
        if parse_decimal(normalized) <= 0:
            raise ValueError("settlement values must be positive")
        return normalized


class CardRefundLegCreate(BaseModel):
    account_id: str
    asset_id: str
    quantity: str
    transaction_value_myr: str
    reference_value_myr: str

    @field_validator("quantity", "transaction_value_myr", "reference_value_myr")
    @classmethod
    def validate_refund_decimal(cls, value: str) -> str:
        normalized = canonical_decimal(value)
        if parse_decimal(normalized) <= 0:
            raise ValueError("refund values must be positive")
        return normalized


class CardRefundCreate(BaseModel):
    external_id: str | None = Field(default=None, max_length=200)
    refund_legs: list[CardRefundLegCreate] = Field(min_length=1)
    refunded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    description: str = Field(default="", max_length=500)


class RewardCreate(BaseModel):
    reward_type: str = Field(default="CASHBACK", max_length=48)
    account_id: str
    asset_id: str
    amount: str
    earned_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    external_id: str | None = Field(default=None, max_length=200)

    @field_validator("amount")
    @classmethod
    def validate_reward_amount(cls, value: str) -> str:
        normalized = canonical_decimal(value)
        if parse_decimal(normalized) <= 0:
            raise ValueError("reward amount must be positive")
        return normalized


class RewardCreditCreate(BaseModel):
    income_account_id: str
    category_id: str | None = None
    value_myr: str
    valuation_rate: str | None = None
    valuation_source: str = Field(min_length=1, max_length=120)
    credited_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("value_myr", "valuation_rate")
    @classmethod
    def validate_credit_decimal(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = canonical_decimal(value)
        if parse_decimal(normalized) <= 0:
            raise ValueError("credited values must be positive")
        return normalized


class JourneyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    journey_type: str = Field(default="FUNDS", pattern="^(FUNDS|PAYMENT|WITHDRAWAL)$")
    status: str = Field(default="DRAFT", pattern="^(DRAFT|CONFIRMED|COMPLETED)$")
    allocation_method: str = Field(min_length=1, max_length=160)
    confidence: str = Field(default="EXACT", pattern="^(EXACT|HIGH|ESTIMATED|MISSING_INPUT)$")
    notes: str = Field(default="", max_length=500)


class JourneyAllocationCreate(BaseModel):
    asset_id: str
    allocation_role: str = Field(pattern="^(INPUT|INTERMEDIATE|OUTPUT|COST)$")
    quantity: str
    value_myr: str
    source: str = Field(min_length=1, max_length=160)
    confidence: str = Field(default="EXACT", pattern="^(EXACT|HIGH|ESTIMATED|MISSING_INPUT)$")

    @field_validator("quantity", "value_myr")
    @classmethod
    def validate_allocation_decimal(cls, value: str) -> str:
        normalized = canonical_decimal(value)
        if parse_decimal(normalized) <= 0:
            raise ValueError("journey allocation values must be positive")
        return normalized


class JourneyEventCreate(BaseModel):
    event_id: str
    relation_type: str = Field(default="STEP", min_length=1, max_length=40)
    sequence: int = Field(default=0, ge=0)
    allocations: list[JourneyAllocationCreate] = Field(min_length=1)


class ChannelPathCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    path_type: str = Field(pattern="^(PAYMENT|WITHDRAWAL)$")
    mode: str = Field(pattern="^(ACTUAL|SIMULATED)$")
    explicit_cost_myr: str
    derived_deviation_myr: str
    cashback_myr: str = "0"
    source: str = Field(min_length=1, max_length=160)
    confidence: str = Field(default="EXACT", pattern="^(EXACT|HIGH|ESTIMATED|MISSING_INPUT)$")

    @field_validator("explicit_cost_myr", "cashback_myr")
    @classmethod
    def validate_nonnegative_path_decimal(cls, value: str) -> str:
        normalized = canonical_decimal(value)
        if parse_decimal(normalized) < 0:
            raise ValueError("explicit costs and cashback must be non-negative")
        return normalized

    @field_validator("derived_deviation_myr")
    @classmethod
    def validate_derived_deviation(cls, value: str) -> str:
        return canonical_decimal(value)


class ChannelComparisonCreate(BaseModel):
    amount_myr: str
    compared_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reference_rate: str
    reference_source: str = Field(min_length=1, max_length=160)
    cashback_eligible: bool = False
    paths: list[ChannelPathCreate] = Field(min_length=2)

    @field_validator("amount_myr", "reference_rate")
    @classmethod
    def validate_comparison_decimal(cls, value: str) -> str:
        normalized = canonical_decimal(value)
        if parse_decimal(normalized) <= 0:
            raise ValueError("comparison amount and reference rate must be positive")
        return normalized


EventRead.model_rebuild()
