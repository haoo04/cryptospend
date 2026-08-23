from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cost_basis import (
    LotAllocation,
    apply_disposals,
    apply_transfers,
    create_cost_lot,
    plan_fifo,
)
from app.enums import AccountType, EntryDirection, EventType, FeeTreatment, RateType
from app.ledger import DomainError, create_draft, post_event, utc_text
from app.models import (
    Account,
    Asset,
    FeeComponent,
    RateSnapshot,
    Trade,
    TradeFill,
    TransactionEvent,
    Transfer,
)
from app.money import micros_to_myr, myr_to_micros, parse_decimal
from app.schemas import EventDraftCreate, FeeCreate, TradeCreate, TransferCreate


def require_asset_account(session: Session, account_id: str) -> Account:
    account = session.get(Account, account_id)
    if account is None or account.account_type != AccountType.ASSET.value:
        raise DomainError("trade and transfer accounts must be ASSET accounts")
    return account


def require_gain_account(session: Session, account_id: str) -> Account:
    account = session.get(Account, account_id)
    if account is None or account.account_type != AccountType.GAIN_LOSS.value:
        raise DomainError("gain_loss_account_id must reference a GAIN_LOSS account")
    return account


def require_expense_account(session: Session, fee: FeeCreate) -> Account:
    if fee.expense_account_id is None:
        raise DomainError("fee expense_account_id is required")
    account = session.get(Account, fee.expense_account_id)
    if account is None or account.account_type != AccountType.EXPENSE.value:
        raise DomainError("fee expense_account_id must reference an EXPENSE account")
    return account


def myr_asset(session: Session) -> Asset:
    asset = session.scalar(select(Asset).where(Asset.symbol == "MYR", Asset.chain.is_(None)))
    if asset is None:
        raise DomainError("MYR asset is required; complete onboarding first", 409)
    return asset


def gain_entry(account_id: str, myr_asset_id: str, gain_micros: int) -> dict | None:
    if gain_micros == 0:
        return None
    amount = micros_to_myr(abs(gain_micros))
    return {
        "account_id": account_id,
        "asset_id": myr_asset_id,
        "direction": EntryDirection.CREDIT if gain_micros > 0 else EntryDirection.DEBIT,
        "quantity": amount,
        "book_amount_myr": amount,
    }


def fee_entries(
    fee: FeeCreate,
    trading_account_id: str,
    fee_basis: int,
    withheld_from_acquired_asset: bool = False,
) -> list[dict]:
    value = myr_to_micros(fee.value_myr)
    result: list[dict] = []
    if fee.accounting_treatment != FeeTreatment.CAPITALIZED:
        expense = require_expense_account_placeholder(fee)
        result.append(
            {
                "account_id": expense,
                "asset_id": fee.asset_id,
                "direction": EntryDirection.DEBIT,
                "quantity": fee.amount,
                "book_amount_myr": fee.value_myr,
            }
        )
    if fee.accounting_treatment != FeeTreatment.REDUCE_PROCEEDS and not withheld_from_acquired_asset:
        result.append(
            {
                "account_id": trading_account_id,
                "asset_id": fee.asset_id,
                "direction": EntryDirection.CREDIT,
                "quantity": fee.amount,
                "book_amount_myr": micros_to_myr(fee_basis),
                "transaction_value_myr": micros_to_myr(value),
            }
        )
    return result


def require_expense_account_placeholder(fee: FeeCreate) -> str:
    if fee.expense_account_id is None:
        raise DomainError("fee expense_account_id is required")
    return fee.expense_account_id


def record_fee(session: Session, event_id: str, fee: FeeCreate) -> FeeComponent:
    component = FeeComponent(
        event_id=event_id,
        component_type=fee.component_type.upper(),
        asset_id=fee.asset_id,
        amount=fee.amount,
        value_myr=myr_to_micros(fee.value_myr),
        source_kind="EXPLICIT",
        included_in_funding_amount=fee.included_in_funding_amount,
        accounting_treatment=fee.accounting_treatment.value,
        calculation_method=fee.calculation_method,
        confidence="EXACT",
    )
    session.add(component)
    return component


def allocation_basis(allocations: list[LotAllocation]) -> int:
    return sum(allocation.basis_myr for allocation in allocations)


def create_trade(session: Session, command: TradeCreate) -> TransactionEvent:
    require_asset_account(session, command.account_id)
    require_gain_account(session, command.gain_loss_account_id)
    sell_asset = session.get(Asset, command.sell_asset_id)
    buy_asset = session.get(Asset, command.buy_asset_id)
    if sell_asset is None or buy_asset is None:
        raise DomainError("trade assets do not exist")
    if sell_asset.id == buy_asset.id:
        raise DomainError("trade assets must differ")

    reservations: dict[str, tuple[Decimal, int]] = {}
    sell_allocations = plan_fifo(
        session, command.account_id, command.sell_asset_id, command.sell_quantity, reservations
    )
    sell_basis = allocation_basis(sell_allocations)
    gross = myr_to_micros(command.gross_value_myr)
    fee_value = myr_to_micros(command.fee.value_myr) if command.fee else 0
    fee_allocations: list[LotAllocation] = []
    fee_basis = 0
    acquisition_basis = gross
    fee_gain = 0
    fee_withheld = False
    if command.fee:
        if command.fee.accounting_treatment != FeeTreatment.CAPITALIZED:
            require_expense_account(session, command.fee)
        if parse_decimal(command.fee.amount) <= 0 or fee_value <= 0:
            raise DomainError("fee amount and value must be positive")
        fee_withheld = command.fee.asset_id == command.buy_asset_id and command.fee.included_in_funding_amount
        if command.fee.accounting_treatment == FeeTreatment.REDUCE_PROCEEDS:
            if command.fee.asset_id != command.buy_asset_id:
                raise DomainError("REDUCE_PROCEEDS fee must use the acquired asset")
            acquisition_basis = gross - fee_value
            if acquisition_basis < 0:
                raise DomainError("fee cannot exceed gross proceeds")
        elif fee_withheld:
            acquisition_basis = (
                gross if command.fee.accounting_treatment == FeeTreatment.CAPITALIZED else gross - fee_value
            )
        else:
            fee_allocations = plan_fifo(
                session, command.account_id, command.fee.asset_id, command.fee.amount, reservations
            )
            fee_basis = allocation_basis(fee_allocations)
            fee_gain = fee_value - fee_basis
            if command.fee.accounting_treatment == FeeTreatment.CAPITALIZED:
                acquisition_basis += fee_value

    sell_gain = gross - sell_basis
    entries: list[dict] = [
        {
            "account_id": command.account_id,
            "asset_id": command.sell_asset_id,
            "direction": EntryDirection.CREDIT,
            "quantity": command.sell_quantity,
            "book_amount_myr": micros_to_myr(sell_basis),
            "transaction_value_myr": command.gross_value_myr,
        },
        {
            "account_id": command.account_id,
            "asset_id": command.buy_asset_id,
            "direction": EntryDirection.DEBIT,
            "quantity": command.buy_quantity,
            "book_amount_myr": micros_to_myr(acquisition_basis),
            "transaction_value_myr": command.gross_value_myr,
        },
    ]
    if command.fee:
        entries.extend(fee_entries(command.fee, command.account_id, fee_basis, fee_withheld))
    gain = gain_entry(command.gain_loss_account_id, myr_asset(session).id, sell_gain + fee_gain)
    if gain:
        entries.append(gain)

    draft = EventDraftCreate(
        event_type=EventType.TRADE,
        occurred_at=command.occurred_at,
        description=command.description or f"Trade {sell_asset.symbol} to {buy_asset.symbol}",
        transaction_value_myr=command.gross_value_myr,
        entries=entries,
    )
    event = post_event(session, create_draft(session, draft))
    fee_reduces_net = command.fee and (
        fee_withheld or command.fee.accounting_treatment == FeeTreatment.REDUCE_PROCEEDS
    )
    net = gross - fee_value if fee_reduces_net else gross
    trade = Trade(
        event_id=event.id,
        account_id=command.account_id,
        sell_asset_id=command.sell_asset_id,
        buy_asset_id=command.buy_asset_id,
        sell_quantity=command.sell_quantity,
        buy_quantity=command.buy_quantity,
        execution_rate=command.execution_rate,
        gross_value_myr=gross,
        net_value_myr=net,
        order_id=command.order_id,
    )
    trade.fills.append(
        TradeFill(
            filled_at=utc_text(command.occurred_at),
            sell_quantity=command.sell_quantity,
            buy_quantity=command.buy_quantity,
            price=command.execution_rate,
            external_id=command.order_id,
        )
    )
    session.add(trade)
    apply_disposals(session, event.id, sell_allocations, gross, "TRADE")
    if fee_allocations:
        apply_disposals(session, event.id, fee_allocations, fee_value, "FEE")
    create_cost_lot(
        session,
        asset_id=command.buy_asset_id,
        account_id=command.account_id,
        source_event_id=event.id,
        acquired_at=event.occurred_at,
        quantity=command.buy_quantity,
        basis_myr=acquisition_basis,
    )
    if command.fee:
        record_fee(session, event.id, command.fee)
    session.add(
        RateSnapshot(
            event_id=event.id,
            base_asset_id=command.sell_asset_id,
            quote_asset_id=command.buy_asset_id,
            rate=command.execution_rate,
            observed_at=event.occurred_at,
            source="TRADE_EXECUTION",
            rate_type=RateType.EXECUTION.value,
            confidence="EXACT",
        )
    )
    session.flush()
    return event


def create_transfer(session: Session, command: TransferCreate) -> TransactionEvent:
    require_asset_account(session, command.source_account_id)
    require_asset_account(session, command.destination_account_id)
    require_gain_account(session, command.gain_loss_account_id)
    if command.source_account_id == command.destination_account_id:
        raise DomainError("source and destination accounts must differ")
    asset = session.get(Asset, command.asset_id)
    if asset is None:
        raise DomainError("transfer asset does not exist")
    sent = parse_decimal(command.sent_quantity)
    received = parse_decimal(command.received_quantity)
    fee_quantity = parse_decimal(command.fee.amount) if command.fee else Decimal(0)
    if command.fee and command.fee.accounting_treatment != FeeTreatment.EXPENSED:
        raise DomainError("transfer fees must use EXPENSED treatment")
    if command.fee and command.fee.asset_id == command.asset_id:
        if sent != received + fee_quantity:
            raise DomainError("same-asset transfer requires sent = received + fee")
    elif sent != received:
        raise DomainError("transfer sent and received quantities must match when fee uses another asset")

    reservations: dict[str, tuple[Decimal, int]] = {}
    transfer_allocations = plan_fifo(
        session, command.source_account_id, command.asset_id, command.received_quantity, reservations
    )
    moved_basis = allocation_basis(transfer_allocations)
    fee_allocations: list[LotAllocation] = []
    fee_basis = 0
    fee_gain = 0
    fee_value = 0
    if command.fee:
        require_expense_account(session, command.fee)
        fee_value = myr_to_micros(command.fee.value_myr)
        fee_allocations = plan_fifo(
            session, command.source_account_id, command.fee.asset_id, command.fee.amount, reservations
        )
        fee_basis = allocation_basis(fee_allocations)
        fee_gain = fee_value - fee_basis

    entries: list[dict] = [
        {
            "account_id": command.destination_account_id,
            "asset_id": command.asset_id,
            "direction": EntryDirection.DEBIT,
            "quantity": command.received_quantity,
            "book_amount_myr": micros_to_myr(moved_basis),
        },
        {
            "account_id": command.source_account_id,
            "asset_id": command.asset_id,
            "direction": EntryDirection.CREDIT,
            "quantity": command.received_quantity,
            "book_amount_myr": micros_to_myr(moved_basis),
        },
    ]
    if command.fee:
        entries.extend(fee_entries(command.fee, command.source_account_id, fee_basis))
        gain = gain_entry(command.gain_loss_account_id, myr_asset(session).id, fee_gain)
        if gain:
            entries.append(gain)
    draft = EventDraftCreate(
        event_type=EventType.TRANSFER,
        occurred_at=command.occurred_at,
        description=command.description or f"Transfer {asset.symbol}",
        transaction_value_myr=micros_to_myr(moved_basis),
        entries=entries,
    )
    event = post_event(session, create_draft(session, draft))
    transfer = Transfer(
        event_id=event.id,
        source_account_id=command.source_account_id,
        destination_account_id=command.destination_account_id,
        asset_id=command.asset_id,
        sent_quantity=command.sent_quantity,
        received_quantity=command.received_quantity,
        network=command.network,
        tx_hash=command.tx_hash,
        match_status="MATCHED",
    )
    session.add(transfer)
    session.flush()
    apply_transfers(session, event, transfer, command.destination_account_id, transfer_allocations)
    if command.fee:
        apply_disposals(session, event.id, fee_allocations, fee_value, "FEE")
        record_fee(session, event.id, command.fee)
    session.flush()
    return event
