from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cost_basis import LotAllocation, apply_disposals, create_cost_lot, plan_fifo
from app.enums import AccountType, CardStatus, EntryDirection, EventType, FeeTreatment, RewardStatus
from app.ledger import (
    DomainError,
    account_balances,
    add_audit,
    create_draft,
    get_event,
    post_event,
    reverse_event,
    utc_text,
)
from app.models import (
    Account,
    Asset,
    CardCostComponent,
    CardFundingLeg,
    CardHold,
    CardTransaction,
    EventLink,
    FeeComponent,
    Reward,
)
from app.money import canonical_decimal, micros_to_myr, myr_to_micros, parse_decimal
from app.schemas import (
    CardAuthorizationCreate,
    CardRefundCreate,
    CardSettlementCreate,
    EventDraftCreate,
    RewardCreate,
    RewardCreditCreate,
)
from app.trading import gain_entry, myr_asset, record_fee, require_expense_account, require_gain_account


def require_asset_account(session: Session, account_id: str) -> Account:
    account = session.get(Account, account_id)
    if account is None or account.account_type != AccountType.ASSET.value:
        raise DomainError("card funding and reward accounts must be ASSET accounts")
    return account


def active_holds(session: Session) -> dict[tuple[str, str], tuple[Decimal, int]]:
    result: dict[tuple[str, str], tuple[Decimal, int]] = {}
    for hold in session.scalars(select(CardHold).where(CardHold.status == "ACTIVE")):
        key = (hold.account_id, hold.asset_id)
        quantity, value = result.get(key, (Decimal(0), 0))
        result[key] = (quantity + parse_decimal(hold.amount), value + hold.value_myr)
    return result


def available_account_balances(
    session: Session, books: dict[str, list[dict[str, str]]]
) -> dict[str, list[dict[str, str]]]:
    available = {account_id: [dict(balance) for balance in balances] for account_id, balances in books.items()}
    symbols = {asset.id: asset.symbol for asset in session.scalars(select(Asset))}
    for (account_id, asset_id), (held_quantity, held_value) in active_holds(session).items():
        balances = available.setdefault(account_id, [])
        balance = next((item for item in balances if item["asset_id"] == asset_id), None)
        if balance is None:
            balance = {
                "asset_id": asset_id,
                "asset_symbol": symbols[asset_id],
                "quantity": "0",
                "book_amount_myr": "0",
            }
            balances.append(balance)
        balance["quantity"] = canonical_decimal(parse_decimal(balance["quantity"]) - held_quantity)
        balance["book_amount_myr"] = micros_to_myr(
            myr_to_micros(balance["book_amount_myr"]) - held_value
        )
    return available


def get_card(session: Session, card_id: str) -> CardTransaction:
    card = session.get(CardTransaction, card_id)
    if card is None:
        raise DomainError("card transaction not found", 404)
    return card


def assert_external_id_available(
    session: Session, provider: str, provider_account_id: str, external_id: str | None
) -> None:
    if external_id is None:
        return
    existing = session.scalar(
        select(CardTransaction.id).where(
            CardTransaction.provider == provider,
            CardTransaction.provider_account_id == provider_account_id,
            CardTransaction.external_id == external_id,
        )
    )
    if existing:
        raise DomainError("card external record already exists", 409)


def create_authorization(session: Session, command: CardAuthorizationCreate) -> CardTransaction:
    require_asset_account(session, command.card_account_id)
    require_asset_account(session, command.hold_account_id)
    for asset_id in {command.merchant_asset_id, command.billing_asset_id, command.hold_asset_id}:
        if session.get(Asset, asset_id) is None:
            raise DomainError("authorization asset does not exist")
    assert_external_id_available(session, command.provider, command.provider_account_id, command.external_id)

    books = account_balances(session)
    available = available_account_balances(session, books)
    book = next(
        (
            balance
            for balance in available.get(command.hold_account_id, [])
            if balance["asset_id"] == command.hold_asset_id
        ),
        None,
    )
    if book is None or parse_decimal(book["quantity"]) < parse_decimal(command.hold_amount):
        raise DomainError("insufficient available balance for card hold", 409)

    card = CardTransaction(
        provider=command.provider.upper(),
        provider_account_id=command.provider_account_id,
        external_id=command.external_id,
        transaction_type="AUTHORIZATION",
        card_account_id=command.card_account_id,
        merchant_name=command.merchant_name,
        merchant_country=command.merchant_country.upper() if command.merchant_country else None,
        merchant_asset_id=command.merchant_asset_id,
        merchant_amount=command.merchant_amount,
        billing_asset_id=command.billing_asset_id,
        billing_amount=command.billing_amount,
        merchant_value_myr=myr_to_micros(command.merchant_value_myr),
        status=CardStatus.AUTHORIZED.value,
        authorized_at=utc_text(command.authorized_at),
    )
    session.add(card)
    session.flush()
    session.add(
        CardHold(
            card_transaction_id=card.id,
            account_id=command.hold_account_id,
            asset_id=command.hold_asset_id,
            amount=command.hold_amount,
            value_myr=myr_to_micros(command.hold_value_myr),
            status="ACTIVE",
        )
    )
    add_audit(session, "CARD_AUTHORIZED", details={"card_transaction_id": card.id})
    session.flush()
    return card


def release_authorization(session: Session, card: CardTransaction) -> CardTransaction:
    if card.transaction_type != "AUTHORIZATION" or card.status != CardStatus.AUTHORIZED.value:
        raise DomainError("only an active authorization can be reversed", 409)
    hold = session.scalar(select(CardHold).where(CardHold.card_transaction_id == card.id))
    if hold and hold.status == "ACTIVE":
        hold.status = "RELEASED"
        hold.released_at = datetime.now(UTC).isoformat()
    card.status = CardStatus.REVERSED.value
    card.reversed = True
    add_audit(session, "CARD_AUTHORIZATION_REVERSED", details={"card_transaction_id": card.id})
    session.flush()
    return card


def allocation_basis(allocations: list[LotAllocation]) -> int:
    return sum(allocation.basis_myr for allocation in allocations)


def create_settlement(session: Session, command: CardSettlementCreate) -> CardTransaction:
    authorization = get_card(session, command.authorization_id) if command.authorization_id else None
    if authorization and (
        authorization.transaction_type != "AUTHORIZATION"
        or authorization.status not in {CardStatus.AUTHORIZED.value, CardStatus.PARTIALLY_SETTLED.value}
    ):
        raise DomainError("authorization cannot accept a settlement", 409)
    require_asset_account(session, command.card_account_id)
    expense_account = session.get(Account, command.expense_account_id)
    if expense_account is None or expense_account.account_type != AccountType.EXPENSE.value:
        raise DomainError("expense_account_id must reference an EXPENSE account")
    require_gain_account(session, command.gain_loss_account_id)
    merchant_asset = session.get(Asset, command.merchant_asset_id)
    billing_asset = session.get(Asset, command.billing_asset_id)
    if merchant_asset is None or billing_asset is None:
        raise DomainError("settlement assets do not exist")
    assert_external_id_available(session, command.provider, command.provider_account_id, command.external_id)

    merchant_value = myr_to_micros(command.merchant_value_myr)
    included_fees = sum(
        (myr_to_micros(fee.value_myr) for fee in command.fees if fee.included_in_funding_amount), 0
    )
    funding_transaction_value = sum(myr_to_micros(leg.transaction_value_myr) for leg in command.funding_legs)
    if funding_transaction_value != merchant_value + included_fees:
        raise DomainError("funding transaction values must equal merchant value plus included fees")
    for fee in command.fees:
        if fee.accounting_treatment != FeeTreatment.EXPENSED:
            raise DomainError("card fees must use EXPENSED treatment")
        require_expense_account(session, fee)
        if not fee.included_in_funding_amount:
            if fee.funding_account_id is None:
                raise DomainError("separate card fees require funding_account_id")
            require_asset_account(session, fee.funding_account_id)

    reservations: dict[str, tuple[Decimal, int]] = {}
    funding_allocations: list[tuple[object, list[LotAllocation], int]] = []
    total_funding_basis = 0
    total_gain = 0
    for leg in command.funding_legs:
        require_asset_account(session, leg.account_id)
        allocations = plan_fifo(session, leg.account_id, leg.asset_id, leg.quantity, reservations)
        basis = allocation_basis(allocations)
        funding_allocations.append((leg, allocations, basis))
        total_funding_basis += basis
        total_gain += myr_to_micros(leg.transaction_value_myr) - basis

    separate_fee_allocations: list[tuple[object, list[LotAllocation], int]] = []
    for fee in command.fees:
        if fee.included_in_funding_amount:
            continue
        allocations = plan_fifo(session, fee.funding_account_id or "", fee.asset_id, fee.amount, reservations)
        basis = allocation_basis(allocations)
        separate_fee_allocations.append((fee, allocations, basis))
        total_gain += myr_to_micros(fee.value_myr) - basis

    entries: list[dict] = [
        {
            "account_id": command.expense_account_id,
            "asset_id": command.merchant_asset_id,
            "direction": EntryDirection.DEBIT,
            "quantity": command.merchant_amount,
            "book_amount_myr": command.merchant_value_myr,
        }
    ]
    for fee in command.fees:
        entries.append(
            {
                "account_id": fee.expense_account_id,
                "asset_id": fee.asset_id,
                "direction": EntryDirection.DEBIT,
                "quantity": fee.amount,
                "book_amount_myr": fee.value_myr,
            }
        )
    for leg, _allocations, basis in funding_allocations:
        entries.append(
            {
                "account_id": leg.account_id,
                "asset_id": leg.asset_id,
                "direction": EntryDirection.CREDIT,
                "quantity": leg.quantity,
                "book_amount_myr": micros_to_myr(basis),
                "transaction_value_myr": leg.transaction_value_myr,
                "reference_value_myr": leg.reference_value_myr,
            }
        )
    for fee, _allocations, basis in separate_fee_allocations:
        entries.append(
            {
                "account_id": fee.funding_account_id,
                "asset_id": fee.asset_id,
                "direction": EntryDirection.CREDIT,
                "quantity": fee.amount,
                "book_amount_myr": micros_to_myr(basis),
                "transaction_value_myr": fee.value_myr,
            }
        )
    gain = gain_entry(command.gain_loss_account_id, myr_asset(session).id, total_gain)
    if gain:
        entries.append(gain)

    event = post_event(
        session,
        create_draft(
            session,
            EventDraftCreate(
                event_type=EventType.CARD_SETTLEMENT,
                occurred_at=command.settled_at,
                description=command.description or f"Card purchase at {command.merchant_name}",
                category_id=command.category_id,
                transaction_value_myr=micros_to_myr(
                    merchant_value + sum(myr_to_micros(f.value_myr) for f in command.fees)
                ),
                entries=entries,
            ),
        ),
    )

    funding_value = sum(myr_to_micros(leg.reference_value_myr) for leg in command.funding_legs)
    separate_fee_value = sum(
        myr_to_micros(fee.value_myr) for fee in command.fees if not fee.included_in_funding_amount
    )
    gross_cost = funding_value + separate_fee_value
    leakage = gross_cost - merchant_value
    explicit_fee_value = sum(myr_to_micros(fee.value_myr) for fee in command.fees)
    actual_fx_rate = canonical_decimal(parse_decimal(command.merchant_amount) / parse_decimal(command.billing_amount))
    fx_deviation = None
    conversion_deviation = None
    confidence = "MISSING_INPUT"
    if command.reference_fx_rate and merchant_asset.symbol == "MYR":
        reference_rate = parse_decimal(command.reference_fx_rate)
        reference_billing = parse_decimal(command.merchant_amount) / reference_rate
        fx_deviation = myr_to_micros((parse_decimal(command.billing_amount) - reference_billing) * reference_rate)
        conversion_deviation = leakage - explicit_fee_value - fx_deviation
        confidence = "HIGH"

    card = CardTransaction(
        event_id=event.id,
        parent_card_transaction_id=authorization.id if authorization else None,
        provider=command.provider.upper(),
        provider_account_id=command.provider_account_id,
        external_id=command.external_id,
        transaction_type="PURCHASE",
        card_account_id=command.card_account_id,
        merchant_name=command.merchant_name,
        merchant_country=command.merchant_country.upper() if command.merchant_country else None,
        merchant_asset_id=command.merchant_asset_id,
        merchant_amount=command.merchant_amount,
        billing_asset_id=command.billing_asset_id,
        billing_amount=command.billing_amount,
        merchant_value_myr=merchant_value,
        funding_value_myr=funding_value,
        separate_fee_value_myr=separate_fee_value,
        gross_economic_cost_myr=gross_cost,
        net_economic_cost_myr=gross_cost,
        total_leakage_myr=leakage,
        actual_fx_rate=actual_fx_rate,
        reference_fx_rate=command.reference_fx_rate,
        fx_deviation_myr=fx_deviation,
        conversion_deviation_myr=conversion_deviation,
        residual_myr=0 if conversion_deviation is not None else None,
        breakdown_confidence=confidence,
        status=CardStatus.SETTLED.value,
        authorized_at=authorization.authorized_at if authorization else None,
        settled_at=utc_text(command.settled_at),
    )
    session.add(card)
    session.flush()
    for sequence, (leg, allocations, basis) in enumerate(funding_allocations):
        apply_disposals(session, event.id, allocations, myr_to_micros(leg.transaction_value_myr), "CARD")
        session.add(
            CardFundingLeg(
                card_transaction_id=card.id,
                event_id=event.id,
                account_id=leg.account_id,
                asset_id=leg.asset_id,
                quantity=leg.quantity,
                transaction_value_myr=myr_to_micros(leg.transaction_value_myr),
                reference_value_myr=myr_to_micros(leg.reference_value_myr),
                book_basis_myr=basis,
                actual_conversion_rate=leg.actual_conversion_rate,
                leg_type="FUNDING",
                sequence=sequence,
            )
        )
    for fee, allocations, _basis in separate_fee_allocations:
        apply_disposals(session, event.id, allocations, myr_to_micros(fee.value_myr), "FEE")
    for fee in command.fees:
        record_fee(session, event.id, fee)
    if fx_deviation is not None:
        card.cost_components.extend(
            [
                CardCostComponent(
                    component_type="FX_DEVIATION",
                    value_myr=fx_deviation,
                    source_kind="DERIVED",
                    calculation_method="(actual billing - merchant/reference FX) × reference FX",
                    confidence="HIGH",
                ),
                CardCostComponent(
                    component_type="CONVERSION_DEVIATION",
                    value_myr=conversion_deviation or 0,
                    source_kind="DERIVED",
                    calculation_method="total leakage - explicit fees - FX deviation",
                    confidence="HIGH",
                ),
            ]
        )
    else:
        card.cost_components.append(
            CardCostComponent(
                component_type="UNCLASSIFIED_DEVIATION",
                value_myr=leakage - explicit_fee_value,
                source_kind="DERIVED",
                calculation_method="total leakage - explicit fees; FX reference missing",
                confidence="MISSING_INPUT",
            )
        )
    if authorization:
        authorization.status = (
            CardStatus.SETTLED.value if command.final_capture else CardStatus.PARTIALLY_SETTLED.value
        )
        hold = session.scalar(select(CardHold).where(CardHold.card_transaction_id == authorization.id))
        if hold and command.final_capture:
            hold.status = "RELEASED"
            hold.released_at = datetime.now(UTC).isoformat()
    add_audit(session, "CARD_SETTLED", event.id, {"card_transaction_id": card.id})
    session.flush()
    return card


def recalculate_card_net(session: Session, settlement: CardTransaction) -> None:
    refunds = session.scalars(
        select(CardTransaction).where(
            CardTransaction.original_transaction_id == settlement.id,
            CardTransaction.transaction_type == "REFUND",
            CardTransaction.reversed.is_(False),
        )
    ).all()
    refund_value = sum(
        leg.reference_value_myr
        for refund in refunds
        for leg in refund.funding_legs
        if not leg.reversed and leg.leg_type == "REFUND"
    )
    cashback = sum(
        reward.value_myr or 0 for reward in settlement.rewards if reward.status == RewardStatus.CREDITED.value
    )
    settlement.net_economic_cost_myr = settlement.gross_economic_cost_myr - refund_value - cashback


def create_refund(session: Session, original: CardTransaction, command: CardRefundCreate) -> CardTransaction:
    if original.transaction_type != "PURCHASE" or original.status not in {
        CardStatus.SETTLED.value,
        CardStatus.PARTIALLY_REFUNDED.value,
    }:
        raise DomainError("only a settled purchase can be refunded", 409)
    expense = session.get(Account, command.expense_account_id)
    if expense is None or expense.account_type != AccountType.EXPENSE.value:
        raise DomainError("expense_account_id must reference an EXPENSE account")
    refund_value = myr_to_micros(command.refund_value_myr)
    if sum(myr_to_micros(leg.transaction_value_myr) for leg in command.refund_legs) != refund_value:
        raise DomainError("refund leg transaction values must equal refund value")
    assert_external_id_available(session, original.provider, original.provider_account_id, command.external_id)
    for leg in command.refund_legs:
        require_asset_account(session, leg.account_id)
        if session.get(Asset, leg.asset_id) is None:
            raise DomainError("refund asset does not exist")

    entries = [
        {
            "account_id": leg.account_id,
            "asset_id": leg.asset_id,
            "direction": EntryDirection.DEBIT,
            "quantity": leg.quantity,
            "book_amount_myr": leg.transaction_value_myr,
            "reference_value_myr": leg.reference_value_myr,
        }
        for leg in command.refund_legs
    ]
    entries.append(
        {
            "account_id": command.expense_account_id,
            "asset_id": myr_asset(session).id,
            "direction": EntryDirection.CREDIT,
            "quantity": command.refund_value_myr,
            "book_amount_myr": command.refund_value_myr,
        }
    )
    event = post_event(
        session,
        create_draft(
            session,
            EventDraftCreate(
                event_type=EventType.CARD_REFUND,
                occurred_at=command.refunded_at,
                description=command.description or f"Refund from {original.merchant_name}",
                category_id=original.event.category_id if original.event else None,
                transaction_value_myr=command.refund_value_myr,
                entries=entries,
            ),
        ),
    )
    refund = CardTransaction(
        event_id=event.id,
        original_transaction_id=original.id,
        provider=original.provider,
        provider_account_id=original.provider_account_id,
        external_id=command.external_id,
        transaction_type="REFUND",
        card_account_id=original.card_account_id,
        merchant_name=original.merchant_name,
        merchant_country=original.merchant_country,
        merchant_asset_id=myr_asset(session).id,
        merchant_amount=command.refund_value_myr,
        billing_asset_id=original.billing_asset_id,
        billing_amount=command.refund_value_myr,
        merchant_value_myr=refund_value,
        funding_value_myr=sum(myr_to_micros(leg.reference_value_myr) for leg in command.refund_legs),
        status=CardStatus.SETTLED.value,
        settled_at=utc_text(command.refunded_at),
    )
    session.add(refund)
    session.flush()
    for sequence, leg in enumerate(command.refund_legs):
        basis = myr_to_micros(leg.transaction_value_myr)
        create_cost_lot(
            session,
            asset_id=leg.asset_id,
            account_id=leg.account_id,
            source_event_id=event.id,
            acquired_at=event.occurred_at,
            quantity=leg.quantity,
            basis_myr=basis,
        )
        session.add(
            CardFundingLeg(
                card_transaction_id=refund.id,
                event_id=event.id,
                account_id=leg.account_id,
                asset_id=leg.asset_id,
                quantity=leg.quantity,
                transaction_value_myr=basis,
                reference_value_myr=myr_to_micros(leg.reference_value_myr),
                book_basis_myr=basis,
                leg_type="REFUND",
                sequence=sequence,
            )
        )
    session.add(EventLink(source_event_id=original.event_id, target_event_id=event.id, relation_type="REFUND"))
    original.status = CardStatus.REFUNDED.value if command.full_refund else CardStatus.PARTIALLY_REFUNDED.value
    recalculate_card_net(session, original)
    add_audit(session, "CARD_REFUNDED", event.id, {"original_card_transaction_id": original.id})
    session.flush()
    return refund


def create_reward(session: Session, card: CardTransaction, command: RewardCreate) -> Reward:
    if card.transaction_type != "PURCHASE" or card.reversed:
        raise DomainError("reward must reference an active settled purchase", 409)
    require_asset_account(session, command.account_id)
    if session.get(Asset, command.asset_id) is None:
        raise DomainError("reward asset does not exist")
    reward = Reward(
        card_transaction_id=card.id,
        reward_type=command.reward_type.upper(),
        account_id=command.account_id,
        asset_id=command.asset_id,
        amount=command.amount,
        status=RewardStatus.PENDING.value,
        earned_at=utc_text(command.earned_at),
        external_id=command.external_id,
    )
    session.add(reward)
    session.flush()
    return reward


def credit_reward(session: Session, reward: Reward, command: RewardCreditCreate) -> Reward:
    if reward.status != RewardStatus.PENDING.value:
        raise DomainError("only a pending reward can be credited", 409)
    income = session.get(Account, command.income_account_id)
    if income is None or income.account_type != AccountType.INCOME.value:
        raise DomainError("income_account_id must reference an INCOME account")
    event = post_event(
        session,
        create_draft(
            session,
            EventDraftCreate(
                event_type=EventType.REWARD,
                occurred_at=command.credited_at,
                description=f"{reward.reward_type.title()} credited",
                category_id=command.category_id,
                transaction_value_myr=command.value_myr,
                entries=[
                    {
                        "account_id": reward.account_id,
                        "asset_id": reward.asset_id,
                        "direction": EntryDirection.DEBIT,
                        "quantity": reward.amount,
                        "book_amount_myr": command.value_myr,
                        "valuation_rate": command.valuation_rate,
                        "valuation_source": command.valuation_source,
                    },
                    {
                        "account_id": command.income_account_id,
                        "asset_id": reward.asset_id,
                        "direction": EntryDirection.CREDIT,
                        "quantity": reward.amount,
                        "book_amount_myr": command.value_myr,
                        "valuation_rate": command.valuation_rate,
                        "valuation_source": command.valuation_source,
                    },
                ],
            ),
        ),
    )
    reward.event_id = event.id
    reward.value_myr = myr_to_micros(command.value_myr)
    reward.status = RewardStatus.CREDITED.value
    reward.credited_at = utc_text(command.credited_at)
    card = reward.card_transaction
    if card.event_id:
        session.add(EventLink(source_event_id=card.event_id, target_event_id=event.id, relation_type="REWARD"))
    recalculate_card_net(session, card)
    session.flush()
    return reward


def reverse_reward(session: Session, reward: Reward, reason: str) -> Reward:
    if reward.status == RewardStatus.PENDING.value:
        reward.status = RewardStatus.REVERSED.value
        reward.reversed_at = datetime.now(UTC).isoformat()
    elif reward.status == RewardStatus.CREDITED.value and reward.event_id:
        reverse_event(session, get_event(session, reward.event_id), reason)
        reward.status = RewardStatus.REVERSED.value
        reward.reversed_at = datetime.now(UTC).isoformat()
    else:
        raise DomainError("reward cannot be reversed", 409)
    recalculate_card_net(session, reward.card_transaction)
    session.flush()
    return reward


def card_cost_report(session: Session) -> list[dict]:
    settlements = session.scalars(
        select(CardTransaction)
        .where(CardTransaction.transaction_type == "PURCHASE", CardTransaction.reversed.is_(False))
        .order_by(CardTransaction.settled_at.desc())
    ).all()
    result = []
    for card in settlements:
        refunds = session.scalars(
            select(CardTransaction).where(
                CardTransaction.original_transaction_id == card.id,
                CardTransaction.transaction_type == "REFUND",
                CardTransaction.reversed.is_(False),
            )
        ).all()
        refunded_value = sum(
            leg.reference_value_myr for refund in refunds for leg in refund.funding_legs if not leg.reversed
        )
        cashback = sum(reward.value_myr or 0 for reward in card.rewards if reward.status == RewardStatus.CREDITED.value)
        fees = session.scalars(
            select(FeeComponent).where(FeeComponent.event_id == card.event_id, FeeComponent.reversed.is_(False))
        ).all()
        result.append(
            {
                "id": card.id,
                "authorization_id": card.parent_card_transaction_id,
                "provider": card.provider,
                "merchant_name": card.merchant_name,
                "merchant_amount": card.merchant_amount,
                "merchant_asset_id": card.merchant_asset_id,
                "merchant_value_myr": micros_to_myr(card.merchant_value_myr),
                "billing_amount": card.billing_amount,
                "billing_asset_id": card.billing_asset_id,
                "funding_value_myr": micros_to_myr(card.funding_value_myr),
                "separate_fee_value_myr": micros_to_myr(card.separate_fee_value_myr),
                "gross_economic_cost_myr": micros_to_myr(card.gross_economic_cost_myr),
                "refunded_value_myr": micros_to_myr(refunded_value),
                "credited_cashback_value_myr": micros_to_myr(cashback),
                "net_economic_cost_myr": micros_to_myr(card.net_economic_cost_myr),
                "total_leakage_myr": micros_to_myr(card.total_leakage_myr),
                "actual_fx_rate": card.actual_fx_rate,
                "reference_fx_rate": card.reference_fx_rate,
                "fx_deviation_myr": micros_to_myr(card.fx_deviation_myr)
                if card.fx_deviation_myr is not None
                else None,
                "conversion_deviation_myr": micros_to_myr(card.conversion_deviation_myr)
                if card.conversion_deviation_myr is not None
                else None,
                "residual_myr": micros_to_myr(card.residual_myr) if card.residual_myr is not None else None,
                "breakdown_confidence": card.breakdown_confidence,
                "status": card.status,
                "settled_at": card.settled_at,
                "funding_legs": [
                    {
                        "asset_id": leg.asset_id,
                        "asset_symbol": leg.asset.symbol,
                        "quantity": leg.quantity,
                        "transaction_value_myr": micros_to_myr(leg.transaction_value_myr),
                        "reference_value_myr": micros_to_myr(leg.reference_value_myr),
                        "book_basis_myr": micros_to_myr(leg.book_basis_myr),
                    }
                    for leg in card.funding_legs
                ],
                "fees": [
                    {
                        "component_type": fee.component_type,
                        "value_myr": micros_to_myr(fee.value_myr),
                        "included_in_funding_amount": fee.included_in_funding_amount,
                    }
                    for fee in fees
                ],
                "components": [
                    {
                        "component_type": component.component_type,
                        "value_myr": micros_to_myr(component.value_myr),
                        "confidence": component.confidence,
                    }
                    for component in card.cost_components
                ],
            }
        )
    return result
