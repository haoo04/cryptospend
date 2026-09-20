import json
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.enums import AccountType, EntryDirection, EventStatus, EventType
from app.models import Account, Asset, AuditLog, Category, FeeComponent, LedgerEntry, TransactionEvent, utc_now_text
from app.money import canonical_decimal, derive_rate_from_micros, micros_to_myr, myr_to_micros, parse_decimal
from app.schemas import MANUAL_EVENT_TYPES, EventDraftCreate, ManualEventCreate


class DomainError(Exception):
    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainError("timestamps must include a timezone")
    return value.astimezone(UTC).isoformat()


def add_audit(session: Session, action: str, event_id: str | None = None, details: dict | None = None) -> None:
    session.add(AuditLog(event_id=event_id, action=action, details=json.dumps(details or {}, sort_keys=True)))


REQUIRED_CATEGORY_EVENT_TYPES = {
    EventType.SALARY.value,
    EventType.INCOME.value,
    EventType.EXPENSE.value,
    EventType.CARD_SETTLEMENT.value,
    EventType.REWARD.value,
}

MANUAL_ACCOUNT_TYPES = {
    EventType.SALARY: ({AccountType.ASSET.value}, {AccountType.INCOME.value}),
    EventType.INCOME: ({AccountType.ASSET.value}, {AccountType.INCOME.value}),
    EventType.OPENING_BALANCE: ({AccountType.ASSET.value}, {AccountType.EQUITY.value}),
    EventType.EXPENSE: ({AccountType.EXPENSE.value}, {AccountType.ASSET.value}),
    EventType.ADJUSTMENT: (
        {
            AccountType.ASSET.value,
            AccountType.EXPENSE.value,
            AccountType.LIABILITY.value,
            AccountType.CLEARING.value,
        },
        {
            AccountType.ASSET.value,
            AccountType.INCOME.value,
            AccountType.EQUITY.value,
            AccountType.GAIN_LOSS.value,
            AccountType.CLEARING.value,
        },
    ),
}


def category_kind_for_account_types(account_types: list[str]) -> str | None:
    kinds = {
        account_type
        for account_type in account_types
        if account_type in {AccountType.INCOME.value, AccountType.EXPENSE.value}
    }
    return next(iter(kinds)) if len(kinds) == 1 else None


def validate_category_binding(
    session: Session,
    category_id: str | None,
    event_type: str,
    account_types: list[str],
    *,
    required: bool = False,
    allow_inactive: bool = False,
) -> Category | None:
    category = session.get(Category, category_id) if category_id else None
    if category_id and category is None:
        raise DomainError("category not found")
    expected_kind = category_kind_for_account_types(account_types)
    if category is not None:
        if not category.active and not allow_inactive:
            raise DomainError("category must be active for a new event")
        if expected_kind is None:
            raise DomainError("category requires exactly one INCOME or EXPENSE account")
        if category.kind != expected_kind:
            raise DomainError(f"category kind must be {expected_kind}")
    if required and category is None:
        raise DomainError(f"category_id is required for {event_type}")
    return category


def create_draft(session: Session, command: EventDraftCreate) -> TransactionEvent:
    account_ids = {entry.account_id for entry in command.entries}
    asset_ids = {entry.asset_id for entry in command.entries}
    accounts = list(session.scalars(select(Account).where(Account.id.in_(account_ids))).all())
    if len(accounts) != len(account_ids):
        raise DomainError("one or more accounts do not exist")
    if len(session.scalars(select(Asset).where(Asset.id.in_(asset_ids))).all()) != len(asset_ids):
        raise DomainError("one or more assets do not exist")

    category = validate_category_binding(
        session,
        command.category_id,
        command.event_type.value,
        [account.account_type for account in accounts if account.id in account_ids],
        allow_inactive=command.event_type == EventType.REVERSAL,
    )
    event = TransactionEvent(
        event_type=command.event_type.value,
        status=EventStatus.DRAFT.value,
        occurred_at=utc_text(command.occurred_at),
        time_precision=command.time_precision,
        description=command.description.strip(),
        category=category.name if category else None,
        category_id=category.id if category else None,
        source=command.source,
        external_id=command.external_id,
        transaction_value_myr=myr_to_micros(command.transaction_value_myr)
        if command.transaction_value_myr is not None
        else None,
        reference_value_myr=myr_to_micros(command.reference_value_myr)
        if command.reference_value_myr is not None
        else None,
    )
    for item in command.entries:
        event.entries.append(
            LedgerEntry(
                account_id=item.account_id,
                asset_id=item.asset_id,
                direction=item.direction.value,
                quantity=canonical_decimal(item.quantity),
                book_amount_myr=myr_to_micros(item.book_amount_myr),
                transaction_value_myr=myr_to_micros(item.transaction_value_myr)
                if item.transaction_value_myr is not None
                else None,
                reference_value_myr=myr_to_micros(item.reference_value_myr)
                if item.reference_value_myr is not None
                else None,
                valuation_rate=canonical_decimal(item.valuation_rate) if item.valuation_rate is not None else None,
                valuation_source=item.valuation_source,
            )
        )
    session.add(event)
    session.flush()
    add_audit(session, "DRAFT_CREATED", event.id)
    return event


def post_event(session: Session, event: TransactionEvent) -> TransactionEvent:
    if event.status != EventStatus.DRAFT.value:
        raise DomainError("only draft events can be posted", 409)
    if len(event.entries) < 2:
        raise DomainError("a posted event requires at least two entries")
    debit = sum(entry.book_amount_myr for entry in event.entries if entry.direction == EntryDirection.DEBIT.value)
    credit = sum(entry.book_amount_myr for entry in event.entries if entry.direction == EntryDirection.CREDIT.value)
    if debit != credit:
        raise DomainError(f"event is not balanced: debit={micros_to_myr(debit)}, credit={micros_to_myr(credit)}")
    for entry in event.entries:
        if parse_decimal(entry.quantity) < 0:
            raise DomainError("entry quantity cannot be negative")
    account_types = [session.get(Account, entry.account_id).account_type for entry in event.entries]
    validate_category_binding(
        session,
        event.category_id,
        event.event_type,
        account_types,
        required=event.event_type in REQUIRED_CATEGORY_EVENT_TYPES,
        allow_inactive=event.event_type == EventType.REVERSAL,
    )
    event.status = EventStatus.POSTED.value
    event.posted_at = utc_now_text()
    from app.cost_basis import create_event_acquisition_lots

    create_event_acquisition_lots(session, event)
    add_audit(session, "EVENT_POSTED", event.id, {"debit_micros": debit, "credit_micros": credit})
    session.flush()
    return event


def create_manual_event(session: Session, command: ManualEventCreate) -> TransactionEvent:
    if command.event_type not in MANUAL_EVENT_TYPES:
        raise DomainError(f"manual {command.event_type.value} is not supported; use its dedicated workflow")
    if command.debit_account_id == command.credit_account_id:
        raise DomainError("manual debit and credit accounts must differ")
    debit_account = session.get(Account, command.debit_account_id)
    credit_account = session.get(Account, command.credit_account_id)
    if debit_account is None or credit_account is None:
        raise DomainError("manual debit and credit accounts must exist")
    allowed_debit, allowed_credit = MANUAL_ACCOUNT_TYPES[command.event_type]
    if debit_account.account_type not in allowed_debit or credit_account.account_type not in allowed_credit:
        if command.event_type == EventType.SALARY or command.event_type == EventType.INCOME:
            raise DomainError("manual SALARY/INCOME requires ASSET debit and INCOME credit")
        if command.event_type == EventType.EXPENSE:
            raise DomainError("manual EXPENSE requires EXPENSE debit and ASSET credit")
        if command.event_type == EventType.OPENING_BALANCE:
            raise DomainError("manual OPENING_BALANCE requires ASSET debit and EQUITY credit")
        raise DomainError("manual ADJUSTMENT account types are not allowed")

    asset = session.get(Asset, command.asset_id)
    if asset is None:
        raise DomainError("manual asset does not exist")
    quantity = parse_decimal(command.quantity)
    book_amount = parse_decimal(command.book_amount_myr)
    if quantity <= 0 or book_amount <= 0:
        raise DomainError("manual quantity and book amount must be positive")

    is_myr = asset.symbol == "MYR" and asset.chain is None
    if is_myr:
        if quantity != book_amount:
            raise DomainError("MYR quantity must equal book amount")
        valuation_rate = None
        valuation_source = None
    else:
        if command.event_type == EventType.EXPENSE:
            raise DomainError("non-MYR EXPENSE requires a disposal-aware flow")
        if command.event_type == EventType.ADJUSTMENT:
            raise DomainError("non-MYR ADJUSTMENT is not supported")
        valuation_source = (command.valuation_source or "").strip()
        if not valuation_source:
            raise DomainError("non-MYR manual acquisition requires valuation_source")
        book_micros = myr_to_micros(command.book_amount_myr)
        try:
            valuation_rate = derive_rate_from_micros(command.quantity, book_micros)
            if command.valuation_rate is not None:
                supplied_rate = parse_decimal(command.valuation_rate)
                if supplied_rate <= 0 or myr_to_micros(quantity * supplied_rate) != book_micros:
                    raise DomainError("valuation_rate conflicts with quantity and book amount")
        except ValueError as exc:
            raise DomainError("valuation_rate must be a finite positive decimal") from exc

    draft = EventDraftCreate(
        event_type=command.event_type,
        occurred_at=command.occurred_at,
        description=command.description,
        category_id=command.category_id,
        transaction_value_myr=command.book_amount_myr,
        entries=[
            {
                "account_id": command.debit_account_id,
                "asset_id": command.asset_id,
                "direction": EntryDirection.DEBIT,
                "quantity": command.quantity,
                "book_amount_myr": command.book_amount_myr,
                "valuation_rate": valuation_rate,
                "valuation_source": valuation_source,
            },
            {
                "account_id": command.credit_account_id,
                "asset_id": command.asset_id,
                "direction": EntryDirection.CREDIT,
                "quantity": command.quantity,
                "book_amount_myr": command.book_amount_myr,
                "valuation_rate": valuation_rate,
                "valuation_source": valuation_source,
            },
        ],
    )
    return post_event(session, create_draft(session, draft))


def get_event(session: Session, event_id: str) -> TransactionEvent:
    event = session.scalar(
        select(TransactionEvent)
        .where(TransactionEvent.id == event_id)
        .options(selectinload(TransactionEvent.entries).selectinload(LedgerEntry.account))
        .options(selectinload(TransactionEvent.entries).selectinload(LedgerEntry.asset))
        .options(selectinload(TransactionEvent.fees).selectinload(FeeComponent.asset))
        .options(selectinload(TransactionEvent.category_ref))
        .options(selectinload(TransactionEvent.receipt))
    )
    if event is None:
        raise DomainError("event not found", 404)
    return event


def reverse_event(session: Session, original: TransactionEvent, reason: str) -> TransactionEvent:
    if original.status != EventStatus.POSTED.value:
        raise DomainError("only posted events can be reversed", 409)
    from app.cost_basis import reverse_cost_projection

    reverse_cost_projection(session, original)
    command = EventDraftCreate(
        event_type=EventType.REVERSAL,
        occurred_at=datetime.now(UTC),
        description=f"Reversal: {reason}",
        source="SYSTEM",
        category_id=original.category_id,
        transaction_value_myr=micros_to_myr(original.transaction_value_myr)
        if original.transaction_value_myr is not None
        else None,
        entries=[
            {
                "account_id": entry.account_id,
                "asset_id": entry.asset_id,
                "direction": (
                    EntryDirection.CREDIT if entry.direction == EntryDirection.DEBIT.value else EntryDirection.DEBIT
                ),
                "quantity": entry.quantity,
                "book_amount_myr": micros_to_myr(entry.book_amount_myr),
                "transaction_value_myr": micros_to_myr(entry.transaction_value_myr)
                if entry.transaction_value_myr is not None
                else None,
                "reference_value_myr": micros_to_myr(entry.reference_value_myr)
                if entry.reference_value_myr is not None
                else None,
                "valuation_rate": entry.valuation_rate,
                "valuation_source": entry.valuation_source,
            }
            for entry in original.entries
        ],
    )
    reversal = create_draft(session, command)
    reversal.reverses_event_id = original.id
    post_event(session, reversal)
    original.status = EventStatus.REVERSED.value
    original.reversed_by_event_id = reversal.id
    add_audit(session, "EVENT_REVERSED", original.id, {"reversal_event_id": reversal.id, "reason": reason})
    session.flush()
    return reversal


def account_balances(session: Session) -> dict[str, list[dict[str, str]]]:
    rows = session.execute(
        select(LedgerEntry, Account, Asset)
        .join(TransactionEvent, TransactionEvent.id == LedgerEntry.event_id)
        .join(Account, Account.id == LedgerEntry.account_id)
        .join(Asset, Asset.id == LedgerEntry.asset_id)
        .where(TransactionEvent.status != EventStatus.DRAFT.value)
    ).all()
    quantities: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    books: dict[tuple[str, str], int] = defaultdict(int)
    symbols: dict[str, str] = {}
    credit_natural = {
        AccountType.LIABILITY.value,
        AccountType.INCOME.value,
        AccountType.EQUITY.value,
        AccountType.GAIN_LOSS.value,
    }
    for entry, account, asset in rows:
        direction_sign = 1 if entry.direction == EntryDirection.DEBIT.value else -1
        natural_sign = -direction_sign if account.account_type in credit_natural else direction_sign
        key = (account.id, asset.id)
        quantities[key] += parse_decimal(entry.quantity) * natural_sign
        books[key] += entry.book_amount_myr * natural_sign
        symbols[asset.id] = asset.symbol
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    for (account_id, asset_id), quantity in quantities.items():
        result[account_id].append(
            {
                "asset_id": asset_id,
                "asset_symbol": symbols[asset_id],
                "quantity": canonical_decimal(quantity),
                "book_amount_myr": micros_to_myr(books[(account_id, asset_id)]),
            }
        )
    return result


def report_totals(session: Session, start: str | None = None, end: str | None = None) -> dict[str, int]:
    statement = (
        select(LedgerEntry, Account)
        .join(TransactionEvent, TransactionEvent.id == LedgerEntry.event_id)
        .join(Account, Account.id == LedgerEntry.account_id)
        .where(TransactionEvent.status != EventStatus.DRAFT.value)
    )
    if start:
        statement = statement.where(TransactionEvent.occurred_at >= start)
    if end:
        statement = statement.where(TransactionEvent.occurred_at < end)
    totals = {"assets": 0, "liabilities": 0, "income": 0, "expense": 0}
    for entry, account in session.execute(statement):
        debit_sign = 1 if entry.direction == EntryDirection.DEBIT.value else -1
        if account.account_type == AccountType.ASSET.value:
            totals["assets"] += entry.book_amount_myr * debit_sign
        elif account.account_type == AccountType.LIABILITY.value:
            totals["liabilities"] -= entry.book_amount_myr * debit_sign
        elif account.account_type == AccountType.INCOME.value:
            totals["income"] -= entry.book_amount_myr * debit_sign
        elif account.account_type == AccountType.EXPENSE.value:
            totals["expense"] += entry.book_amount_myr * debit_sign
    return totals
