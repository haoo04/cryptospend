from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.enums import AccountType, EntryDirection, EventType, RecurringFrequency, RecurringOccurrenceAction
from app.ledger import DomainError, add_audit, create_draft, post_event, utc_now_text
from app.models import (
    Account,
    Asset,
    Category,
    RecurringExpense,
    RecurringExpenseOccurrence,
    Setting,
)
from app.money import micros_to_myr, myr_to_micros
from app.schemas import (
    EventDraftCreate,
    RecurringExpenseCreate,
    RecurringExpenseRecordCreate,
    RecurringExpenseSkipCreate,
    RecurringExpenseUpdate,
)


def advance_due_on(frequency: str | RecurringFrequency, due_on: date, anchor_on: date) -> date:
    frequency_value = frequency.value if isinstance(frequency, RecurringFrequency) else frequency
    if frequency_value == RecurringFrequency.WEEKLY.value:
        return due_on + timedelta(days=7)
    if frequency_value == RecurringFrequency.MONTHLY.value:
        year = due_on.year + (1 if due_on.month == 12 else 0)
        month = 1 if due_on.month == 12 else due_on.month + 1
        return date(year, month, min(anchor_on.day, monthrange(year, month)[1]))
    if frequency_value == RecurringFrequency.YEARLY.value:
        year = due_on.year + 1
        return date(year, anchor_on.month, min(anchor_on.day, monthrange(year, anchor_on.month)[1]))
    raise DomainError("frequency must be WEEKLY, MONTHLY, or YEARLY")


def _annualized_micros(amount_micros: int, frequency: str) -> int:
    if frequency == RecurringFrequency.WEEKLY.value:
        return amount_micros * 52
    if frequency == RecurringFrequency.MONTHLY.value:
        return amount_micros * 12
    return amount_micros


def _timezone(session: Session) -> tuple[str, ZoneInfo]:
    setting = session.get(Setting, "default")
    timezone = setting.timezone if setting else "Asia/Kuala_Lumpur"
    try:
        return timezone, ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise DomainError(f"configured timezone is unavailable: {timezone}") from exc


def _today(session: Session) -> tuple[str, date]:
    timezone, zone = _timezone(session)
    return timezone, datetime.now(zone).date()


def _due_status(expense: RecurringExpense, today: date) -> str:
    if not expense.active:
        return "PAUSED"
    due_on = date.fromisoformat(expense.next_due_on)
    if due_on < today:
        return "OVERDUE"
    if due_on == today:
        return "DUE_TODAY"
    return "UPCOMING"


def _status_sort_key(status: str) -> int:
    return {"OVERDUE": 0, "DUE_TODAY": 1, "UPCOMING": 2, "PAUSED": 3}[status]


def _get_expense(session: Session, recurring_expense_id: str) -> RecurringExpense:
    expense = session.scalar(
        select(RecurringExpense)
        .where(RecurringExpense.id == recurring_expense_id)
        .options(
            selectinload(RecurringExpense.asset),
            selectinload(RecurringExpense.funding_account),
            selectinload(RecurringExpense.expense_account),
            selectinload(RecurringExpense.category_ref),
        )
    )
    if expense is None:
        raise DomainError("recurring expense not found", 404)
    return expense


def _validate_asset(session: Session, asset_id: str, invalid_status: int = 422) -> Asset:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise DomainError("asset_id not found", 404)
    if not asset.active or asset.symbol.upper() != "MYR":
        raise DomainError("asset_id must reference an active MYR asset", invalid_status)
    return asset


def _validate_account(
    session: Session, account_id: str, field: str, expected_type: str, invalid_status: int = 422
) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise DomainError(f"{field} not found", 404)
    if account.closed or account.account_type != expected_type:
        raise DomainError(f"{field} must reference an open {expected_type} account", invalid_status)
    return account


def _validate_category(session: Session, category_id: str, invalid_status: int = 422) -> Category:
    category = session.get(Category, category_id)
    if category is None:
        raise DomainError("category_id not found", 404)
    if not category.active or category.kind != "EXPENSE":
        raise DomainError("category_id must reference an active EXPENSE category", invalid_status)
    return category


def _validate_configuration(
    session: Session,
    *,
    asset_id: str,
    funding_account_id: str,
    expense_account_id: str,
    category_id: str,
    invalid_status: int = 422,
) -> tuple[Asset, Account, Account, Category]:
    return (
        _validate_asset(session, asset_id, invalid_status),
        _validate_account(session, funding_account_id, "funding_account_id", AccountType.ASSET.value, invalid_status),
        _validate_account(
            session, expense_account_id, "expense_account_id", AccountType.EXPENSE.value, invalid_status
        ),
        _validate_category(session, category_id, invalid_status),
    )


def _positive_amount_micros(amount: str) -> int:
    amount_micros = myr_to_micros(amount)
    if amount_micros <= 0:
        raise DomainError("amount_myr must be greater than zero")
    return amount_micros


def recurring_expense_read(session: Session, expense: RecurringExpense) -> dict[str, object]:
    _timezone_name, today = _today(session)
    return {
        "id": expense.id,
        "name": expense.name,
        "amount_myr": micros_to_myr(expense.amount_myr),
        "frequency": expense.frequency,
        "anchor_on": expense.anchor_on,
        "next_due_on": expense.next_due_on,
        "due_status": _due_status(expense, today),
        "annualized_amount_myr": micros_to_myr(_annualized_micros(expense.amount_myr, expense.frequency)),
        "asset_id": expense.asset_id,
        "funding_account_id": expense.funding_account_id,
        "expense_account_id": expense.expense_account_id,
        "category_id": expense.category_id,
        "active": expense.active,
        "created_at": expense.created_at,
        "updated_at": expense.updated_at,
    }


def list_recurring_expenses(session: Session, include_inactive: bool = False) -> dict[str, object]:
    timezone, today = _today(session)
    statement = select(RecurringExpense).options(
        selectinload(RecurringExpense.asset),
        selectinload(RecurringExpense.funding_account),
        selectinload(RecurringExpense.expense_account),
        selectinload(RecurringExpense.category_ref),
    )
    if not include_inactive:
        statement = statement.where(RecurringExpense.active.is_(True))
    expenses = list(session.scalars(statement).all())

    all_active = [expense for expense in expenses if expense.active]
    weekly_total = sum(
        expense.amount_myr for expense in all_active if expense.frequency == RecurringFrequency.WEEKLY.value
    )
    monthly_total = sum(
        expense.amount_myr for expense in all_active if expense.frequency == RecurringFrequency.MONTHLY.value
    )
    yearly_total = sum(
        expense.amount_myr for expense in all_active if expense.frequency == RecurringFrequency.YEARLY.value
    )
    overdue_count = sum(_due_status(expense, today) == "OVERDUE" for expense in all_active)
    items = sorted(
        expenses,
        key=lambda expense: (
            _status_sort_key(_due_status(expense, today)),
            expense.next_due_on,
            expense.name.casefold(),
            expense.id,
        ),
    )
    return {
        "as_of": today.isoformat(),
        "timezone": timezone,
        "summary": {
            "active_count": len(all_active),
            "overdue_count": overdue_count,
            "weekly_total_myr": micros_to_myr(weekly_total),
            "monthly_total_myr": micros_to_myr(monthly_total),
            "yearly_total_myr": micros_to_myr(yearly_total),
            "annualized_myr": micros_to_myr(weekly_total * 52 + monthly_total * 12 + yearly_total),
        },
        "items": [recurring_expense_read(session, expense) for expense in items],
    }


def create_recurring_expense(session: Session, payload: RecurringExpenseCreate) -> RecurringExpense:
    _validate_configuration(
        session,
        asset_id=payload.asset_id,
        funding_account_id=payload.funding_account_id,
        expense_account_id=payload.expense_account_id,
        category_id=payload.category_id,
    )
    amount_micros = _positive_amount_micros(payload.amount_myr)
    due_on = payload.first_due_on.isoformat()
    expense = RecurringExpense(
        name=payload.name,
        amount_myr=amount_micros,
        frequency=payload.frequency.value,
        anchor_on=due_on,
        next_due_on=due_on,
        asset_id=payload.asset_id,
        funding_account_id=payload.funding_account_id,
        expense_account_id=payload.expense_account_id,
        category_id=payload.category_id,
        active=True,
    )
    session.add(expense)
    session.flush()
    add_audit(
        session,
        "RECURRING_EXPENSE_CREATED",
        details={"recurring_expense_id": expense.id, "next_due_on": due_on},
    )
    return expense


def update_recurring_expense(
    session: Session, recurring_expense_id: str, payload: RecurringExpenseUpdate
) -> RecurringExpense:
    expense = _get_expense(session, recurring_expense_id)
    fields = payload.model_fields_set
    resetting_schedule = "frequency" in fields and "next_due_on" in fields
    latest_due = session.scalar(
        select(func.max(RecurringExpenseOccurrence.due_on)).where(
            RecurringExpenseOccurrence.recurring_expense_id == expense.id
        )
    )
    if resetting_schedule and latest_due is not None and payload.next_due_on.isoformat() <= latest_due:
        raise DomainError("next_due_on must be later than the latest handled occurrence", 409)

    next_asset_id = payload.asset_id if "asset_id" in fields else expense.asset_id
    next_funding_account_id = (
        payload.funding_account_id if "funding_account_id" in fields else expense.funding_account_id
    )
    next_expense_account_id = (
        payload.expense_account_id if "expense_account_id" in fields else expense.expense_account_id
    )
    next_category_id = payload.category_id if "category_id" in fields else expense.category_id
    next_active = payload.active if "active" in fields else expense.active
    resuming = "active" in fields and payload.active is True and not expense.active
    if next_active or any(
        field in fields for field in ("asset_id", "funding_account_id", "expense_account_id", "category_id")
    ):
        _validate_configuration(
            session,
            asset_id=next_asset_id,
            funding_account_id=next_funding_account_id,
            expense_account_id=next_expense_account_id,
            category_id=next_category_id,
            invalid_status=409 if resuming else 422,
        )

    if "name" in fields:
        expense.name = payload.name
    if "amount_myr" in fields:
        expense.amount_myr = _positive_amount_micros(payload.amount_myr)
    if resetting_schedule:
        expense.frequency = payload.frequency.value
        expense.anchor_on = payload.next_due_on.isoformat()
        expense.next_due_on = payload.next_due_on.isoformat()
    if "asset_id" in fields:
        expense.asset_id = payload.asset_id
    if "funding_account_id" in fields:
        expense.funding_account_id = payload.funding_account_id
    if "expense_account_id" in fields:
        expense.expense_account_id = payload.expense_account_id
    if "category_id" in fields:
        expense.category_id = payload.category_id
    if "active" in fields:
        expense.active = payload.active
    expense.updated_at = utc_now_text()
    add_audit(
        session,
        "RECURRING_EXPENSE_UPDATED",
        details={
            "recurring_expense_id": expense.id,
            "changed_fields": sorted(fields),
            "next_due_on": expense.next_due_on,
        },
    )
    session.flush()
    return expense


def _validate_current_due(expense: RecurringExpense, due_on: date) -> None:
    if not expense.active:
        raise DomainError("recurring expense is paused", 409)
    if due_on.isoformat() != expense.next_due_on:
        raise DomainError("due_on no longer matches the current next_due_on", 409)


def record_recurring_expense(
    session: Session, recurring_expense_id: str, payload: RecurringExpenseRecordCreate
) -> tuple[RecurringExpense, RecurringExpenseOccurrence]:
    expense = _get_expense(session, recurring_expense_id)
    _validate_current_due(expense, payload.due_on)
    existing = session.scalar(
        select(RecurringExpenseOccurrence).where(
            RecurringExpenseOccurrence.recurring_expense_id == expense.id,
            RecurringExpenseOccurrence.due_on == expense.next_due_on,
        )
    )
    if existing is not None:
        raise DomainError("this occurrence has already been handled", 409)
    asset, funding_account, expense_account, category = _validate_configuration(
        session,
        asset_id=expense.asset_id,
        funding_account_id=expense.funding_account_id,
        expense_account_id=expense.expense_account_id,
        category_id=expense.category_id,
    )
    amount = micros_to_myr(expense.amount_myr)
    external_id = f"recurring-expense:{expense.id}:{expense.next_due_on}"
    event = post_event(
        session,
        create_draft(
            session,
            EventDraftCreate(
                event_type=EventType.EXPENSE,
                occurred_at=payload.occurred_at,
                description=expense.name,
                category_id=category.id,
                source="RECURRING_EXPENSE",
                external_id=external_id,
                transaction_value_myr=amount,
                entries=[
                    {
                        "account_id": expense_account.id,
                        "asset_id": asset.id,
                        "direction": EntryDirection.DEBIT,
                        "quantity": amount,
                        "book_amount_myr": amount,
                    },
                    {
                        "account_id": funding_account.id,
                        "asset_id": asset.id,
                        "direction": EntryDirection.CREDIT,
                        "quantity": amount,
                        "book_amount_myr": amount,
                    },
                ],
            ),
        ),
    )
    occurrence = RecurringExpenseOccurrence(
        recurring_expense_id=expense.id,
        due_on=expense.next_due_on,
        action=RecurringOccurrenceAction.RECORDED.value,
        scheduled_amount_myr=expense.amount_myr,
        event_id=event.id,
        handled_at=utc_now_text(),
    )
    expense.next_due_on = advance_due_on(
        expense.frequency, date.fromisoformat(expense.next_due_on), date.fromisoformat(expense.anchor_on)
    ).isoformat()
    expense.updated_at = utc_now_text()
    session.add(occurrence)
    session.flush()
    add_audit(
        session,
        "RECURRING_EXPENSE_RECORDED",
        event.id,
        {"recurring_expense_id": expense.id, "due_on": occurrence.due_on, "occurrence_id": occurrence.id},
    )
    session.flush()
    return expense, occurrence


def skip_recurring_expense(
    session: Session, recurring_expense_id: str, payload: RecurringExpenseSkipCreate
) -> tuple[RecurringExpense, RecurringExpenseOccurrence]:
    expense = _get_expense(session, recurring_expense_id)
    _validate_current_due(expense, payload.due_on)
    existing = session.scalar(
        select(RecurringExpenseOccurrence).where(
            RecurringExpenseOccurrence.recurring_expense_id == expense.id,
            RecurringExpenseOccurrence.due_on == expense.next_due_on,
        )
    )
    if existing is not None:
        raise DomainError("this occurrence has already been handled", 409)
    occurrence = RecurringExpenseOccurrence(
        recurring_expense_id=expense.id,
        due_on=expense.next_due_on,
        action=RecurringOccurrenceAction.SKIPPED.value,
        scheduled_amount_myr=expense.amount_myr,
        skip_reason=payload.reason,
        handled_at=utc_now_text(),
    )
    expense.next_due_on = advance_due_on(
        expense.frequency, date.fromisoformat(expense.next_due_on), date.fromisoformat(expense.anchor_on)
    ).isoformat()
    expense.updated_at = utc_now_text()
    session.add(occurrence)
    session.flush()
    add_audit(
        session,
        "RECURRING_EXPENSE_SKIPPED",
        details={
            "recurring_expense_id": expense.id,
            "due_on": occurrence.due_on,
            "occurrence_id": occurrence.id,
        },
    )
    session.flush()
    return expense, occurrence


def _occurrence_read(occurrence: RecurringExpenseOccurrence) -> dict[str, object]:
    event = occurrence.event
    return {
        "id": occurrence.id,
        "recurring_expense_id": occurrence.recurring_expense_id,
        "due_on": occurrence.due_on,
        "action": occurrence.action,
        "scheduled_amount_myr": micros_to_myr(occurrence.scheduled_amount_myr),
        "event_id": occurrence.event_id,
        "event_status": event.status if event else None,
        "occurred_at": event.occurred_at if event else None,
        "skip_reason": occurrence.skip_reason,
        "handled_at": occurrence.handled_at,
    }


def get_occurrence(session: Session, occurrence_id: str) -> RecurringExpenseOccurrence:
    occurrence = session.scalar(
        select(RecurringExpenseOccurrence)
        .where(RecurringExpenseOccurrence.id == occurrence_id)
        .options(selectinload(RecurringExpenseOccurrence.event))
    )
    if occurrence is None:
        raise DomainError("recurring expense occurrence not found", 404)
    return occurrence


def occurrence_read(session: Session, occurrence_id: str) -> dict[str, object]:
    return _occurrence_read(get_occurrence(session, occurrence_id))


def list_occurrences(session: Session, recurring_expense_id: str, limit: int = 50) -> list[dict[str, object]]:
    _get_expense(session, recurring_expense_id)
    occurrences = session.scalars(
        select(RecurringExpenseOccurrence)
        .where(RecurringExpenseOccurrence.recurring_expense_id == recurring_expense_id)
        .options(selectinload(RecurringExpenseOccurrence.event))
        .order_by(RecurringExpenseOccurrence.due_on.desc(), RecurringExpenseOccurrence.handled_at.desc())
        .limit(limit)
    ).all()
    return [_occurrence_read(occurrence) for occurrence in occurrences]
