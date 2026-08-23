from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import AccountType, EntryDirection, EventType, RateType
from app.models import (
    Account,
    Asset,
    CostLot,
    FeeComponent,
    LedgerEntry,
    LotDisposal,
    LotTransfer,
    RateSnapshot,
    Trade,
    TransactionEvent,
    Transfer,
)
from app.money import MYR_MICROS, canonical_decimal, micros_to_myr, myr_to_micros, parse_decimal


@dataclass
class LotAllocation:
    lot: CostLot
    quantity: Decimal
    basis_myr: int


def plan_fifo(
    session: Session,
    account_id: str,
    asset_id: str,
    quantity: str | Decimal,
    reservations: dict[str, tuple[Decimal, int]] | None = None,
) -> list[LotAllocation]:
    from app.ledger import DomainError

    needed = parse_decimal(quantity)
    if needed <= 0:
        raise DomainError("disposal quantity must be positive")
    reserved = reservations if reservations is not None else {}
    lots = session.scalars(
        select(CostLot)
        .where(
            CostLot.account_id == account_id,
            CostLot.asset_id == asset_id,
            CostLot.voided.is_(False),
        )
        .order_by(CostLot.acquired_at, CostLot.id)
    ).all()
    allocations: list[LotAllocation] = []
    for lot in lots:
        reserved_quantity, reserved_basis = reserved.get(lot.id, (Decimal(0), 0))
        available_quantity = parse_decimal(lot.remaining_quantity) - reserved_quantity
        available_basis = lot.remaining_basis_myr - reserved_basis
        if available_quantity <= 0:
            continue
        if lot.basis_status != "KNOWN":
            raise DomainError("cost basis is unknown for one or more FIFO lots", 409)
        take = min(needed, available_quantity)
        if take == available_quantity:
            basis = available_basis
        else:
            basis = int(
                (Decimal(available_basis) * take / available_quantity).quantize(
                    Decimal("1"), rounding=ROUND_HALF_EVEN
                )
            )
        allocations.append(LotAllocation(lot=lot, quantity=take, basis_myr=basis))
        reserved[lot.id] = (reserved_quantity + take, reserved_basis + basis)
        needed -= take
        if needed == 0:
            break
    if needed != 0:
        raise DomainError(f"insufficient FIFO quantity; missing {canonical_decimal(needed)}", 409)
    return allocations


def split_micros(total: int, quantities: list[Decimal]) -> list[int]:
    if not quantities:
        return []
    quantity_total = sum(quantities, Decimal(0))
    allocated = 0
    result: list[int] = []
    for index, quantity in enumerate(quantities):
        if index == len(quantities) - 1:
            value = total - allocated
        else:
            value = int(
                (Decimal(total) * quantity / quantity_total).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
            )
            allocated += value
        result.append(value)
    return result


def apply_disposals(
    session: Session,
    event_id: str,
    allocations: list[LotAllocation],
    proceeds_myr: int,
    purpose: str,
) -> tuple[int, int]:
    proceeds = split_micros(proceeds_myr, [allocation.quantity for allocation in allocations])
    total_basis = 0
    total_gain = 0
    for allocation, allocated_proceeds in zip(allocations, proceeds, strict=True):
        lot = allocation.lot
        lot.remaining_quantity = canonical_decimal(parse_decimal(lot.remaining_quantity) - allocation.quantity)
        lot.remaining_basis_myr -= allocation.basis_myr
        gain = allocated_proceeds - allocation.basis_myr
        session.add(
            LotDisposal(
                event_id=event_id,
                cost_lot_id=lot.id,
                quantity=canonical_decimal(allocation.quantity),
                basis_myr=allocation.basis_myr,
                proceeds_myr=allocated_proceeds,
                realized_gain_loss_myr=gain,
                purpose=purpose,
            )
        )
        total_basis += allocation.basis_myr
        total_gain += gain
    return total_basis, total_gain


def create_cost_lot(
    session: Session,
    *,
    asset_id: str,
    account_id: str,
    source_event_id: str,
    acquired_at: str,
    quantity: str | Decimal,
    basis_myr: int,
    parent_lot_id: str | None = None,
) -> CostLot:
    normalized_quantity = canonical_decimal(quantity)
    lot = CostLot(
        asset_id=asset_id,
        account_id=account_id,
        source_event_id=source_event_id,
        parent_lot_id=parent_lot_id,
        acquired_at=acquired_at,
        original_quantity=normalized_quantity,
        remaining_quantity=normalized_quantity,
        basis_myr=basis_myr,
        remaining_basis_myr=basis_myr,
        basis_status="BASIS_UNKNOWN" if basis_myr == 0 and parse_decimal(normalized_quantity) > 0 else "KNOWN",
    )
    session.add(lot)
    session.flush()
    return lot


def apply_transfers(
    session: Session,
    event: TransactionEvent,
    transfer: Transfer,
    destination_account_id: str,
    allocations: list[LotAllocation],
) -> int:
    total_basis = 0
    for allocation in allocations:
        source_lot = allocation.lot
        source_lot.remaining_quantity = canonical_decimal(
            parse_decimal(source_lot.remaining_quantity) - allocation.quantity
        )
        source_lot.remaining_basis_myr -= allocation.basis_myr
        destination_lot = create_cost_lot(
            session,
            asset_id=source_lot.asset_id,
            account_id=destination_account_id,
            source_event_id=event.id,
            acquired_at=source_lot.acquired_at,
            quantity=allocation.quantity,
            basis_myr=allocation.basis_myr,
            parent_lot_id=source_lot.id,
        )
        session.add(
            LotTransfer(
                event_id=event.id,
                transfer_id=transfer.id,
                source_lot_id=source_lot.id,
                destination_lot_id=destination_lot.id,
                quantity=canonical_decimal(allocation.quantity),
                basis_myr=allocation.basis_myr,
            )
        )
        total_basis += allocation.basis_myr
    return total_basis


def create_event_acquisition_lots(session: Session, event: TransactionEvent) -> None:
    acquisition_types = {
        EventType.OPENING_BALANCE.value,
        EventType.SALARY.value,
        EventType.INCOME.value,
        EventType.REWARD.value,
    }
    if event.event_type not in acquisition_types:
        return
    if session.scalar(select(CostLot.id).where(CostLot.source_event_id == event.id)) is not None:
        return
    myr_asset = session.scalar(select(Asset).where(Asset.symbol == "MYR", Asset.chain.is_(None)))
    for entry in event.entries:
        account = session.get(Account, entry.account_id)
        if account is None or account.account_type != AccountType.ASSET.value:
            continue
        if entry.direction != EntryDirection.DEBIT.value or parse_decimal(entry.quantity) <= 0:
            continue
        create_cost_lot(
            session,
            asset_id=entry.asset_id,
            account_id=entry.account_id,
            source_event_id=event.id,
            acquired_at=event.occurred_at,
            quantity=entry.quantity,
            basis_myr=entry.book_amount_myr,
        )
        if entry.valuation_rate and entry.valuation_source and myr_asset and entry.asset_id != myr_asset.id:
            session.add(
                RateSnapshot(
                    event_id=event.id,
                    base_asset_id=entry.asset_id,
                    quote_asset_id=myr_asset.id,
                    rate=entry.valuation_rate,
                    observed_at=event.occurred_at,
                    source=entry.valuation_source,
                    rate_type=RateType.MANUAL.value,
                )
            )


def reverse_cost_projection(session: Session, event: TransactionEvent) -> None:
    from app.ledger import DomainError

    disposals = session.scalars(
        select(LotDisposal).where(LotDisposal.event_id == event.id, LotDisposal.reversed.is_(False))
    ).all()
    for disposal in disposals:
        lot = session.get(CostLot, disposal.cost_lot_id)
        if lot is None:
            raise DomainError("cost lot projection is incomplete", 409)
        lot.remaining_quantity = canonical_decimal(
            parse_decimal(lot.remaining_quantity) + parse_decimal(disposal.quantity)
        )
        lot.remaining_basis_myr += disposal.basis_myr
        disposal.reversed = True

    transfers = session.scalars(
        select(LotTransfer).where(LotTransfer.event_id == event.id, LotTransfer.reversed.is_(False))
    ).all()
    for allocation in transfers:
        source = session.get(CostLot, allocation.source_lot_id)
        destination = session.get(CostLot, allocation.destination_lot_id)
        if source is None or destination is None:
            raise DomainError("lot transfer projection is incomplete", 409)
        if parse_decimal(destination.remaining_quantity) != parse_decimal(destination.original_quantity):
            raise DomainError("cannot reverse a transfer after its destination lot has been used", 409)
        source.remaining_quantity = canonical_decimal(
            parse_decimal(source.remaining_quantity) + parse_decimal(allocation.quantity)
        )
        source.remaining_basis_myr += allocation.basis_myr
        destination.remaining_quantity = "0"
        destination.remaining_basis_myr = 0
        destination.voided = True
        allocation.reversed = True

    acquired_lots = session.scalars(
        select(CostLot).where(
            CostLot.source_event_id == event.id,
            CostLot.parent_lot_id.is_(None),
            CostLot.voided.is_(False),
        )
    ).all()
    for lot in acquired_lots:
        if parse_decimal(lot.remaining_quantity) != parse_decimal(lot.original_quantity):
            raise DomainError("cannot reverse an acquisition after its cost lot has been used", 409)
        lot.remaining_quantity = "0"
        lot.remaining_basis_myr = 0
        lot.voided = True

    for model in (Trade, Transfer, FeeComponent):
        records = session.scalars(select(model).where(model.event_id == event.id, model.reversed.is_(False))).all()
        for record in records:
            record.reversed = True


def portfolio_positions(session: Session) -> list[dict[str, str | bool | None]]:
    rows = session.execute(
        select(LedgerEntry, Account, Asset)
        .join(TransactionEvent, TransactionEvent.id == LedgerEntry.event_id)
        .join(Account, Account.id == LedgerEntry.account_id)
        .join(Asset, Asset.id == LedgerEntry.asset_id)
        .where(TransactionEvent.status != "DRAFT", Account.account_type == AccountType.ASSET.value)
    ).all()
    quantities: dict[str, Decimal] = {}
    assets: dict[str, Asset] = {}
    for entry, _account, asset in rows:
        sign = Decimal(1) if entry.direction == EntryDirection.DEBIT.value else Decimal(-1)
        quantities[asset.id] = quantities.get(asset.id, Decimal(0)) + parse_decimal(entry.quantity) * sign
        assets[asset.id] = asset

    lot_rows = session.scalars(select(CostLot).where(CostLot.voided.is_(False))).all()
    cost_basis: dict[str, int] = {}
    lot_quantities: dict[str, Decimal] = {}
    complete: dict[str, bool] = {}
    for lot in lot_rows:
        cost_basis[lot.asset_id] = cost_basis.get(lot.asset_id, 0) + lot.remaining_basis_myr
        lot_quantities[lot.asset_id] = lot_quantities.get(lot.asset_id, Decimal(0)) + parse_decimal(
            lot.remaining_quantity
        )
        complete[lot.asset_id] = complete.get(lot.asset_id, True) and lot.basis_status == "KNOWN"

    realized: dict[str, int] = {}
    for disposal, lot in session.execute(
        select(LotDisposal, CostLot)
        .join(CostLot, CostLot.id == LotDisposal.cost_lot_id)
        .where(LotDisposal.reversed.is_(False))
    ):
        realized[lot.asset_id] = realized.get(lot.asset_id, 0) + disposal.realized_gain_loss_myr
        assets[lot.asset_id] = lot.asset

    myr_asset = session.scalar(select(Asset).where(Asset.symbol == "MYR", Asset.chain.is_(None)))
    rates: dict[str, str] = {}
    if myr_asset:
        for rate in session.scalars(
            select(RateSnapshot)
            .where(RateSnapshot.quote_asset_id == myr_asset.id)
            .order_by(RateSnapshot.observed_at.desc())
        ):
            rates.setdefault(rate.base_asset_id, rate.rate)
        rates[myr_asset.id] = "1"

    positions: list[dict[str, str | bool | None]] = []
    for asset_id in sorted(set(quantities) | set(realized), key=lambda item: assets[item].symbol):
        quantity = quantities.get(asset_id, Decimal(0))
        basis = cost_basis.get(asset_id, 0)
        rate = rates.get(asset_id)
        market_value = myr_to_micros(quantity * parse_decimal(rate)) if rate is not None else None
        average = Decimal(basis) / MYR_MICROS / quantity if quantity > 0 else None
        basis_complete = complete.get(asset_id, quantity == 0) and lot_quantities.get(asset_id, Decimal(0)) == quantity
        positions.append(
            {
                "asset_id": asset_id,
                "symbol": assets[asset_id].symbol,
                "quantity": canonical_decimal(quantity),
                "cost_basis_myr": micros_to_myr(basis),
                "average_cost_myr": canonical_decimal(average) if average is not None else None,
                "market_rate_myr": rate,
                "market_value_myr": micros_to_myr(market_value) if market_value is not None else None,
                "unrealized_gain_loss_myr": micros_to_myr(market_value - basis) if market_value is not None else None,
                "realized_gain_loss_myr": micros_to_myr(realized.get(asset_id, 0)),
                "basis_complete": basis_complete,
            }
        )
    return positions
