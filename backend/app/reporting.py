from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.cost_basis import event_effective_at, portfolio_positions
from app.enums import AccountType, EntryDirection, EventStatus, EventType
from app.ledger import DomainError, add_audit, report_totals, utc_text
from app.models import (
    Asset,
    CardCostComponent,
    CardTransaction,
    FeeComponent,
    Journey,
    JourneyAllocation,
    JourneyEventLink,
    LedgerEntry,
    ReportSnapshot,
    Setting,
    TransactionEvent,
)
from app.money import canonical_decimal, micros_to_myr, myr_to_micros, parse_decimal
from app.schemas import ChannelComparisonCreate, JourneyCreate, JourneyEventCreate

CONFIDENCE_RANK = {"EXACT": 0, "HIGH": 1, "ESTIMATED": 2, "MISSING_INPUT": 3}


def month_bounds(session: Session, month: str) -> tuple[str, str, str]:
    if len(month) != 7 or month[4] != "-":
        raise DomainError("month must use YYYY-MM format")
    try:
        year, month_number = (int(part) for part in month.split("-"))
        local_start = datetime(year, month_number, 1)
    except (TypeError, ValueError) as exc:
        raise DomainError("month must use YYYY-MM format") from exc
    setting = session.get(Setting, "default")
    timezone = setting.timezone if setting else "Asia/Kuala_Lumpur"
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise DomainError(f"configured timezone is unavailable: {timezone}") from exc
    local_start = local_start.replace(tzinfo=zone)
    if month_number == 12:
        local_end = datetime(year + 1, 1, 1, tzinfo=zone)
    else:
        local_end = datetime(year, month_number + 1, 1, tzinfo=zone)
    return utc_text(local_start), utc_text(local_end), timezone


def fee_report_data(session: Session, start: str | None = None, end: str | None = None) -> dict:
    totals: dict[str, int] = defaultdict(int)
    for fee, event in session.execute(
        select(FeeComponent, TransactionEvent).join(TransactionEvent, TransactionEvent.id == FeeComponent.event_id)
    ):
        if start is not None and event.occurred_at < start:
            continue
        if end is not None and event.occurred_at >= end:
            continue
        if not event_effective_at(session, event, end):
            continue
        totals[fee.component_type] += fee.value_myr
    components = [
        {"component_type": component_type, "value_myr": micros_to_myr(value)}
        for component_type, value in sorted(totals.items())
    ]
    return {"total_myr": micros_to_myr(sum(totals.values())), "components": components}


def fee_leakage_data(session: Session, start: str | None = None, end: str | None = None) -> dict:
    components = []
    explicit_total = 0
    for fee, event in session.execute(
        select(FeeComponent, TransactionEvent).join(TransactionEvent, TransactionEvent.id == FeeComponent.event_id)
    ):
        if start is not None and event.occurred_at < start:
            continue
        if end is not None and event.occurred_at >= end:
            continue
        if not event_effective_at(session, event, end):
            continue
        explicit_total += fee.value_myr
        components.append(
            {
                "component_type": fee.component_type,
                "value_myr": micros_to_myr(fee.value_myr),
                "source_kind": fee.source_kind,
                "source": event.source,
                "calculation_method": fee.calculation_method or "Recorded explicit fee",
                "confidence": fee.confidence,
            }
        )

    derived_total = 0
    derived_rows = session.execute(
        select(CardCostComponent, CardTransaction, TransactionEvent)
        .join(CardTransaction, CardTransaction.id == CardCostComponent.card_transaction_id)
        .join(TransactionEvent, TransactionEvent.id == CardTransaction.event_id)
    )
    for component, card, event in derived_rows:
        if start is not None and event.occurred_at < start:
            continue
        if end is not None and event.occurred_at >= end:
            continue
        if not event_effective_at(session, event, end):
            continue
        derived_total += component.value_myr
        components.append(
            {
                "component_type": component.component_type,
                "value_myr": micros_to_myr(component.value_myr),
                "source_kind": component.source_kind,
                "source": card.provider,
                "calculation_method": component.calculation_method,
                "confidence": component.confidence,
            }
        )
    return {
        "explicit_myr": micros_to_myr(explicit_total),
        "derived_myr": micros_to_myr(derived_total),
        "total_leakage_myr": micros_to_myr(explicit_total + derived_total),
        "components": components,
    }


def event_channel(session: Session, event: TransactionEvent) -> str:
    if event.event_type in {EventType.CARD_SETTLEMENT.value, EventType.CARD_REFUND.value, EventType.REWARD.value}:
        return "CRYPTO_CARD"
    if event.reverses_event_id:
        original = session.get(TransactionEvent, event.reverses_event_id)
        if original is not None:
            return event_channel(session, original)
    asset_accounts = [entry.account for entry in event.entries if entry.account.account_type == AccountType.ASSET.value]
    for account in asset_accounts:
        if account.channel_type != "OTHER":
            return account.channel_type
    return "OTHER"


def spending_by_channel(session: Session, start: str, end: str) -> list[dict[str, str]]:
    statement = (
        select(TransactionEvent)
        .where(
            TransactionEvent.status != EventStatus.DRAFT.value,
            TransactionEvent.occurred_at >= start,
            TransactionEvent.occurred_at < end,
        )
        .options(selectinload(TransactionEvent.entries).selectinload(LedgerEntry.account))
        .order_by(TransactionEvent.occurred_at)
    )
    values: dict[str, dict[str, int]] = defaultdict(lambda: {"gross": 0, "refunds": 0, "cashback": 0})
    for event in session.scalars(statement):
        channel = event_channel(session, event)
        expense = 0
        for entry in event.entries:
            if entry.account.account_type != AccountType.EXPENSE.value:
                continue
            sign = 1 if entry.direction == EntryDirection.DEBIT.value else -1
            expense += entry.book_amount_myr * sign
        if expense >= 0:
            values[channel]["gross"] += expense
        else:
            values[channel]["refunds"] -= expense

        is_reward = event.event_type == EventType.REWARD.value
        if event.reverses_event_id:
            original = session.get(TransactionEvent, event.reverses_event_id)
            is_reward = original is not None and original.event_type == EventType.REWARD.value
        if is_reward:
            for entry in event.entries:
                if entry.account.account_type != AccountType.INCOME.value:
                    continue
                sign = 1 if entry.direction == EntryDirection.CREDIT.value else -1
                values[channel]["cashback"] += entry.book_amount_myr * sign

    result = []
    for channel, amounts in sorted(values.items()):
        if not any(amounts.values()):
            continue
        net = amounts["gross"] - amounts["refunds"] - amounts["cashback"]
        result.append(
            {
                "channel_type": channel,
                "gross_spending_myr": micros_to_myr(amounts["gross"]),
                "refunds_myr": micros_to_myr(amounts["refunds"]),
                "cashback_myr": micros_to_myr(amounts["cashback"]),
                "net_spending_myr": micros_to_myr(net),
                "source": "Posted ledger entries",
                "calculation_method": "gross expense - refunds - credited cashback",
                "confidence": "EXACT",
            }
        )
    return result


def monthly_report(session: Session, month: str) -> dict:
    start, end, timezone = month_bounds(session, month)
    period = report_totals(session, start, end)
    lifetime = report_totals(session, end=end)
    channels = spending_by_channel(session, start, end)
    gross = sum(myr_to_micros(row["gross_spending_myr"]) for row in channels)
    net = sum(myr_to_micros(row["net_spending_myr"]) for row in channels)
    return {
        "month": month,
        "timezone": timezone,
        "period_start": start,
        "period_end": end,
        "summary": {
            "net_worth_myr": micros_to_myr(lifetime["assets"] - lifetime["liabilities"]),
            "income_myr": micros_to_myr(period["income"]),
            "expense_myr": micros_to_myr(period["expense"]),
            "gross_spending_myr": micros_to_myr(gross),
            "net_spending_myr": micros_to_myr(net),
        },
        "fees": fee_report_data(session, start, end),
        "fee_leakage": fee_leakage_data(session, start, end),
        "channels": channels,
        "portfolio": portfolio_positions(session, end),
    }


def snapshot_metadata(snapshot: ReportSnapshot) -> dict[str, str]:
    return {
        "id": snapshot.id,
        "snapshot_type": snapshot.snapshot_type,
        "period_key": snapshot.period_key,
        "period_start": snapshot.period_start,
        "as_of": snapshot.as_of,
        "timezone": snapshot.timezone,
        "checksum": snapshot.checksum,
        "created_at": snapshot.created_at,
    }


def create_monthly_snapshot(session: Session, month: str) -> dict:
    report = monthly_report(session, month)
    payload = json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    snapshot = ReportSnapshot(
        snapshot_type="MONTHLY",
        period_key=month,
        period_start=report["period_start"],
        as_of=report["period_end"],
        timezone=report["timezone"],
        payload=payload,
        checksum=sha256(payload.encode("utf-8")).hexdigest(),
    )
    session.add(snapshot)
    session.flush()
    add_audit(session, "MONTHLY_SNAPSHOT_CREATED", details={"snapshot_id": snapshot.id, "month": month})
    return {**snapshot_metadata(snapshot), "report": report}


def list_snapshots(session: Session) -> list[dict[str, str]]:
    return [
        snapshot_metadata(snapshot)
        for snapshot in session.scalars(select(ReportSnapshot).order_by(ReportSnapshot.created_at.desc()))
    ]


def get_snapshot(session: Session, snapshot_id: str) -> dict:
    snapshot = session.get(ReportSnapshot, snapshot_id)
    if snapshot is None:
        raise DomainError("report snapshot not found", 404)
    return {**snapshot_metadata(snapshot), "report": json.loads(snapshot.payload)}


def create_journey(session: Session, command: JourneyCreate) -> Journey:
    journey = Journey(
        name=command.name.strip(),
        journey_type=command.journey_type,
        status=command.status,
        allocation_method=command.allocation_method.strip(),
        confidence=command.confidence,
        notes=command.notes.strip(),
    )
    session.add(journey)
    session.flush()
    add_audit(session, "JOURNEY_CREATED", details={"journey_id": journey.id})
    return journey


def get_journey(session: Session, journey_id: str) -> Journey:
    journey = session.scalar(
        select(Journey)
        .where(Journey.id == journey_id)
        .execution_options(populate_existing=True)
        .options(
            selectinload(Journey.event_links)
            .selectinload(JourneyEventLink.allocations)
            .selectinload(JourneyAllocation.asset),
            selectinload(Journey.event_links)
            .selectinload(JourneyEventLink.event)
            .selectinload(TransactionEvent.entries)
            .selectinload(LedgerEntry.account),
        )
    )
    if journey is None:
        raise DomainError("journey not found", 404)
    return journey


def add_journey_event(session: Session, journey: Journey, command: JourneyEventCreate) -> JourneyEventLink:
    event = session.scalar(
        select(TransactionEvent)
        .where(TransactionEvent.id == command.event_id)
        .options(selectinload(TransactionEvent.entries).selectinload(LedgerEntry.account))
    )
    if event is None:
        raise DomainError("event not found", 404)
    if event.status == EventStatus.DRAFT.value:
        raise DomainError("draft events cannot be allocated to a journey", 409)
    duplicate = session.scalar(
        select(JourneyEventLink.id).where(
            JourneyEventLink.journey_id == journey.id,
            JourneyEventLink.event_id == event.id,
        )
    )
    if duplicate:
        raise DomainError("event is already linked to this journey", 409)

    capacity_quantity: dict[str, Decimal] = {}
    capacity_value: dict[str, int] = {}
    for asset_id in {entry.asset_id for entry in event.entries}:
        debits = [entry for entry in event.entries if entry.asset_id == asset_id and entry.direction == "DEBIT"]
        credits = [entry for entry in event.entries if entry.asset_id == asset_id and entry.direction == "CREDIT"]
        capacity_quantity[asset_id] = max(
            sum((parse_decimal(entry.quantity) for entry in debits), Decimal()),
            sum((parse_decimal(entry.quantity) for entry in credits), Decimal()),
        )
        capacity_value[asset_id] = max(
            sum(entry.book_amount_myr for entry in debits),
            sum(entry.book_amount_myr for entry in credits),
        )

    used_quantity: dict[str, Decimal] = defaultdict(Decimal)
    used_value: dict[str, int] = defaultdict(int)
    existing = session.scalars(
        select(JourneyAllocation)
        .join(JourneyEventLink, JourneyEventLink.id == JourneyAllocation.event_link_id)
        .where(JourneyEventLink.event_id == event.id)
    )
    for allocation in existing:
        used_quantity[allocation.asset_id] += parse_decimal(allocation.quantity)
        used_value[allocation.asset_id] += allocation.value_myr

    new_quantity: dict[str, Decimal] = defaultdict(Decimal)
    new_value: dict[str, int] = defaultdict(int)
    for allocation in command.allocations:
        if allocation.asset_id not in capacity_quantity or session.get(Asset, allocation.asset_id) is None:
            raise DomainError("journey allocation asset is not present in the event")
        new_quantity[allocation.asset_id] += parse_decimal(allocation.quantity)
        new_value[allocation.asset_id] += myr_to_micros(allocation.value_myr)
    for asset_id in new_quantity:
        if used_quantity[asset_id] + new_quantity[asset_id] > capacity_quantity[asset_id]:
            raise DomainError("journey allocation exceeds the event quantity", 409)
        if used_value[asset_id] + new_value[asset_id] > capacity_value[asset_id]:
            raise DomainError("journey allocation exceeds the event MYR value", 409)

    link = JourneyEventLink(
        journey_id=journey.id,
        event_id=event.id,
        relation_type=command.relation_type.strip(),
        sequence=command.sequence,
    )
    for item in command.allocations:
        link.allocations.append(
            JourneyAllocation(
                asset_id=item.asset_id,
                allocation_role=item.allocation_role,
                quantity=canonical_decimal(item.quantity),
                value_myr=myr_to_micros(item.value_myr),
                source=item.source.strip(),
                confidence=item.confidence,
            )
        )
    session.add(link)
    session.flush()
    add_audit(session, "JOURNEY_EVENT_ALLOCATED", event.id, {"journey_id": journey.id, "link_id": link.id})
    return link


def journey_report(session: Session, journey_id: str, as_of: str | None = None) -> dict:
    journey = get_journey(session, journey_id)
    totals = {"INPUT": 0, "INTERMEDIATE": 0, "OUTPUT": 0, "COST": 0}
    confidence = journey.confidence
    rows = []
    for link in sorted(journey.event_links, key=lambda item: (item.sequence, item.event.occurred_at, item.id)):
        active = event_effective_at(session, link.event, as_of)
        for allocation in link.allocations:
            if active:
                totals[allocation.allocation_role] += allocation.value_myr
                if CONFIDENCE_RANK[allocation.confidence] > CONFIDENCE_RANK[confidence]:
                    confidence = allocation.confidence
            rows.append(
                {
                    "id": allocation.id,
                    "event_id": link.event_id,
                    "event_type": link.event.event_type,
                    "event_description": link.event.description,
                    "occurred_at": link.event.occurred_at,
                    "relation_type": link.relation_type,
                    "sequence": link.sequence,
                    "asset_id": allocation.asset_id,
                    "asset_symbol": allocation.asset.symbol,
                    "allocation_role": allocation.allocation_role,
                    "quantity": allocation.quantity,
                    "value_myr": micros_to_myr(allocation.value_myr),
                    "source": allocation.source,
                    "confidence": allocation.confidence,
                    "active_at_query": active,
                }
            )
    if totals["INPUT"] == 0 or totals["OUTPUT"] == 0:
        confidence = "MISSING_INPUT"
    derived = totals["INPUT"] - totals["OUTPUT"] - totals["COST"]
    return {
        "id": journey.id,
        "name": journey.name,
        "journey_type": journey.journey_type,
        "status": journey.status,
        "allocation_method": journey.allocation_method,
        "notes": journey.notes,
        "gross_input_myr": micros_to_myr(totals["INPUT"]),
        "net_output_myr": micros_to_myr(totals["OUTPUT"]),
        "explicit_cost_myr": micros_to_myr(totals["COST"]),
        "derived_deviation_myr": micros_to_myr(derived),
        "total_path_cost_myr": micros_to_myr(totals["INPUT"] - totals["OUTPUT"]),
        "calculation_method": "gross input - net output - explicit allocated costs",
        "source": "Manual journey allocations over posted ledger events",
        "confidence": confidence,
        "as_of": as_of,
        "allocations": rows,
    }


def compare_channels(command: ChannelComparisonCreate) -> dict:
    path_types = {path.path_type for path in command.paths}
    if len(path_types) != 1:
        raise DomainError("all compared paths must have the same path type")
    amount = myr_to_micros(command.amount_myr)
    results = []
    for path in command.paths:
        explicit = myr_to_micros(path.explicit_cost_myr)
        derived = myr_to_micros(path.derived_deviation_myr)
        cashback = myr_to_micros(path.cashback_myr) if command.cashback_eligible else 0
        effective_cost = explicit + derived - cashback
        cost_rate = Decimal(effective_cost) * Decimal(100) / Decimal(amount)
        results.append(
            {
                "name": path.name,
                "path_type": path.path_type,
                "mode": path.mode,
                "explicit_cost_myr": micros_to_myr(explicit),
                "derived_deviation_myr": micros_to_myr(derived),
                "cashback_myr": micros_to_myr(cashback),
                "effective_cost_myr": micros_to_myr(effective_cost),
                "net_value_myr": micros_to_myr(amount - effective_cost),
                "cost_rate_percent": canonical_decimal(cost_rate),
                "source": path.source,
                "confidence": path.confidence,
            }
        )
    lowest = min(myr_to_micros(row["effective_cost_myr"]) for row in results)
    for row in results:
        row["is_lowest_cost"] = myr_to_micros(row["effective_cost_myr"]) == lowest
    return {
        "fixed_conditions": {
            "amount_myr": command.amount_myr,
            "compared_at": utc_text(command.compared_at),
            "reference_rate": command.reference_rate,
            "reference_source": command.reference_source,
            "cashback_eligible": command.cashback_eligible,
        },
        "paths": results,
        "note": "ACTUAL uses observed inputs; SIMULATED is a counterfactual supplied by the user.",
    }
