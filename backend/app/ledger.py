import json
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.enums import AccountType, EntryDirection, EventStatus, EventType
from app.models import Account, Asset, AuditLog, LedgerEntry, TransactionEvent, utc_now_text
from app.money import canonical_decimal, micros_to_myr, myr_to_micros, parse_decimal
from app.schemas import EventDraftCreate, ManualEventCreate


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


def create_draft(session: Session, command: EventDraftCreate) -> TransactionEvent:
    account_ids = {entry.account_id for entry in command.entries}
    asset_ids = {entry.asset_id for entry in command.entries}
    if len(session.scalars(select(Account).where(Account.id.in_(account_ids))).all()) != len(account_ids):
        raise DomainError("one or more accounts do not exist")
    if len(session.scalars(select(Asset).where(Asset.id.in_(asset_ids))).all()) != len(asset_ids):
        raise DomainError("one or more assets do not exist")

    event = TransactionEvent(
        event_type=command.event_type.value,
        status=EventStatus.DRAFT.value,
        occurred_at=utc_text(command.occurred_at),
        time_precision=command.time_precision,
        description=command.description.strip(),
        category=command.category.strip() if command.category else None,
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
    event.status = EventStatus.POSTED.value
    event.posted_at = utc_now_text()
    add_audit(session, "EVENT_POSTED", event.id, {"debit_micros": debit, "credit_micros": credit})
    session.flush()
    return event


def create_manual_event(session: Session, command: ManualEventCreate) -> TransactionEvent:
    draft = EventDraftCreate(
        event_type=command.event_type,
        occurred_at=command.occurred_at,
        description=command.description,
        category=command.category,
        transaction_value_myr=command.book_amount_myr,
        entries=[
            {
                "account_id": command.debit_account_id,
                "asset_id": command.asset_id,
                "direction": EntryDirection.DEBIT,
                "quantity": command.quantity,
                "book_amount_myr": command.book_amount_myr,
                "valuation_rate": command.valuation_rate,
                "valuation_source": command.valuation_source,
            },
            {
                "account_id": command.credit_account_id,
                "asset_id": command.asset_id,
                "direction": EntryDirection.CREDIT,
                "quantity": command.quantity,
                "book_amount_myr": command.book_amount_myr,
                "valuation_rate": command.valuation_rate,
                "valuation_source": command.valuation_source,
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
    )
    if event is None:
        raise DomainError("event not found", 404)
    return event


def reverse_event(session: Session, original: TransactionEvent, reason: str) -> TransactionEvent:
    if original.status != EventStatus.POSTED.value:
        raise DomainError("only posted events can be reversed", 409)
    command = EventDraftCreate(
        event_type=EventType.REVERSAL,
        occurred_at=datetime.now(UTC),
        description=f"Reversal: {reason}",
        source="SYSTEM",
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
