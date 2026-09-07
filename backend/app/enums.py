from enum import StrEnum


class AccountType(StrEnum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"
    EQUITY = "EQUITY"
    GAIN_LOSS = "GAIN_LOSS"
    CLEARING = "CLEARING"


class AccountChannel(StrEnum):
    BANK = "BANK"
    CASH = "CASH"
    EWALLET = "EWALLET"
    EXCHANGE = "EXCHANGE"
    CRYPTO_WALLET = "CRYPTO_WALLET"
    CARD = "CARD"
    OTHER = "OTHER"


class EventStatus(StrEnum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"


class EventType(StrEnum):
    OPENING_BALANCE = "OPENING_BALANCE"
    SALARY = "SALARY"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"
    TRANSFER = "TRANSFER"
    TRADE = "TRADE"
    CARD_SETTLEMENT = "CARD_SETTLEMENT"
    CARD_REFUND = "CARD_REFUND"
    REWARD = "REWARD"
    FEE = "FEE"
    ADJUSTMENT = "ADJUSTMENT"
    REVERSAL = "REVERSAL"


class CategoryKind(StrEnum):
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


class EntryDirection(StrEnum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class FeeSourceKind(StrEnum):
    EXPLICIT = "EXPLICIT"
    DERIVED = "DERIVED"


class FeeTreatment(StrEnum):
    CAPITALIZED = "CAPITALIZED"
    REDUCE_PROCEEDS = "REDUCE_PROCEEDS"
    EXPENSED = "EXPENSED"


class Confidence(StrEnum):
    EXACT = "EXACT"
    HIGH = "HIGH"
    ESTIMATED = "ESTIMATED"
    MISSING_INPUT = "MISSING_INPUT"


class RateType(StrEnum):
    EXECUTION = "EXECUTION"
    SETTLEMENT = "SETTLEMENT"
    PROVIDER = "PROVIDER"
    MARKET = "MARKET"
    CARD_NETWORK = "CARD_NETWORK"
    MANUAL = "MANUAL"
    CROSS = "CROSS"


class CardStatus(StrEnum):
    AUTHORIZED = "AUTHORIZED"
    SETTLED = "SETTLED"
    PARTIALLY_SETTLED = "PARTIALLY_SETTLED"
    REVERSED = "REVERSED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"


class RewardStatus(StrEnum):
    PENDING = "PENDING"
    CREDITED = "CREDITED"
    REVERSED = "REVERSED"
    EXPIRED = "EXPIRED"


class ImportStatus(StrEnum):
    PREVIEWED = "PREVIEWED"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"


class ReconciliationStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    IGNORED = "IGNORED"
