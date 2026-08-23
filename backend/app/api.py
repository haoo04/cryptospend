from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.cards import (
    available_account_balances,
    card_cost_report,
    create_authorization,
    create_refund,
    create_reward,
    create_settlement,
    credit_reward,
    get_card,
    release_authorization,
    reverse_reward,
)
from app.cost_basis import portfolio_positions
from app.database import get_session
from app.enums import AccountChannel, AccountType
from app.ledger import (
    DomainError,
    account_balances,
    add_audit,
    create_draft,
    create_manual_event,
    get_event,
    post_event,
    report_totals,
    reverse_event,
    utc_text,
)
from app.models import (
    Account,
    Asset,
    CardHold,
    CardTransaction,
    CostLot,
    Journey,
    LedgerEntry,
    RateSnapshot,
    Reward,
    Setting,
    TransactionEvent,
)
from app.money import micros_to_myr, myr_to_micros
from app.reporting import (
    add_journey_event,
    compare_channels,
    create_journey,
    create_monthly_snapshot,
    fee_leakage_data,
    fee_report_data,
    get_journey,
    get_snapshot,
    journey_report,
    list_snapshots,
    monthly_report,
    spending_by_channel,
)
from app.schemas import (
    AccountCreate,
    AccountRead,
    AssetCreate,
    AssetRead,
    CardAuthorizationCreate,
    CardRefundCreate,
    CardSettlementCreate,
    ChannelComparisonCreate,
    CostLotRead,
    EventDraftCreate,
    EventRead,
    JourneyCreate,
    JourneyEventCreate,
    ManualEventCreate,
    OnboardingCreate,
    PortfolioPositionRead,
    RateCreate,
    ReverseCreate,
    RewardCreate,
    RewardCreditCreate,
    SettingsRead,
    SummaryRead,
    TradeCreate,
    TransferCreate,
)
from app.trading import create_trade, create_transfer

router = APIRouter(prefix="/api")


def event_read(event: TransactionEvent) -> EventRead:
    return EventRead(
        id=event.id,
        event_type=event.event_type,
        status=event.status,
        occurred_at=event.occurred_at,
        time_precision=event.time_precision,
        description=event.description,
        category=event.category,
        source=event.source,
        external_id=event.external_id,
        transaction_value_myr=micros_to_myr(event.transaction_value_myr)
        if event.transaction_value_myr is not None
        else None,
        reference_value_myr=micros_to_myr(event.reference_value_myr)
        if event.reference_value_myr is not None
        else None,
        reverses_event_id=event.reverses_event_id,
        reversed_by_event_id=event.reversed_by_event_id,
        posted_at=event.posted_at,
        entries=[
            {
                "id": entry.id,
                "account_id": entry.account_id,
                "account_name": entry.account.name,
                "asset_id": entry.asset_id,
                "asset_symbol": entry.asset.symbol,
                "direction": entry.direction,
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
            for entry in event.entries
        ],
        fees=[
            {
                "id": fee.id,
                "component_type": fee.component_type,
                "asset_id": fee.asset_id,
                "asset_symbol": fee.asset.symbol,
                "amount": fee.amount,
                "value_myr": micros_to_myr(fee.value_myr),
                "source_kind": fee.source_kind,
                "included_in_funding_amount": fee.included_in_funding_amount,
                "accounting_treatment": fee.accounting_treatment,
                "calculation_method": fee.calculation_method,
                "confidence": fee.confidence,
            }
            for fee in event.fees
        ],
    )


@router.get("/assets", response_model=list[AssetRead])
def list_assets(session: Session = Depends(get_session)) -> list[Asset]:
    return list(session.scalars(select(Asset).order_by(Asset.symbol, Asset.chain)).all())


@router.post("/assets", response_model=AssetRead, status_code=201)
def create_asset(payload: AssetCreate, session: Session = Depends(get_session)) -> Asset:
    asset = Asset(**payload.model_dump())
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


@router.get("/accounts", response_model=list[AccountRead])
def list_accounts(session: Session = Depends(get_session)) -> list[dict]:
    balances = account_balances(session)
    available = available_account_balances(session, balances)
    return [
        {
            "id": account.id,
            "name": account.name,
            "account_type": account.account_type,
            "channel_type": account.channel_type,
            "provider": account.provider,
            "closed": account.closed,
            "balances": balances.get(account.id, []),
            "available_balances": available.get(account.id, []),
        }
        for account in session.scalars(select(Account).order_by(Account.account_type, Account.name))
    ]


@router.post("/accounts", response_model=AccountRead, status_code=201)
def create_account(payload: AccountCreate, session: Session = Depends(get_session)) -> dict:
    account = Account(
        name=payload.name.strip(),
        account_type=payload.account_type.value,
        channel_type=payload.channel_type.value,
        provider=payload.provider,
    )
    session.add(account)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DomainError("an account with this identity already exists", 409) from exc
    return {
        "id": account.id,
        "name": account.name,
        "account_type": account.account_type,
        "channel_type": account.channel_type,
        "provider": account.provider,
        "closed": account.closed,
        "balances": [],
        "available_balances": [],
    }


@router.post("/onboarding", response_model=SettingsRead)
def onboarding(payload: OnboardingCreate, session: Session = Depends(get_session)) -> Setting:
    setting = session.get(Setting, "default")
    if setting is None:
        setting = Setting(id="default")
        session.add(setting)
    setting.reporting_currency = payload.reporting_currency.strip().upper()
    setting.timezone = payload.timezone.strip()

    defaults = [
        ("MYR", "Malaysian Ringgit", 6),
        ("USD", "US Dollar", 6),
        ("USDT", "Tether", 18),
        ("BTC", "Bitcoin", 18),
        ("ETH", "Ether", 18),
    ]
    existing_symbols = set(session.scalars(select(Asset.symbol).where(Asset.chain.is_(None))))
    for symbol, name, decimals in defaults:
        if symbol not in existing_symbols:
            session.add(Asset(symbol=symbol, name=name, decimals=decimals))

    requested_accounts = payload.accounts or [
        AccountCreate(name="Bank", account_type=AccountType.ASSET, channel_type=AccountChannel.BANK),
        AccountCreate(name="Cash", account_type=AccountType.ASSET, channel_type=AccountChannel.CASH),
        AccountCreate(
            name="Crypto Wallet", account_type=AccountType.ASSET, channel_type=AccountChannel.CRYPTO_WALLET
        ),
        AccountCreate(name="Salary", account_type=AccountType.INCOME),
        AccountCreate(name="Other Income", account_type=AccountType.INCOME),
        AccountCreate(name="General Expense", account_type=AccountType.EXPENSE),
        AccountCreate(name="Trading Fees", account_type=AccountType.EXPENSE),
        AccountCreate(name="Network Fees", account_type=AccountType.EXPENSE),
        AccountCreate(name="Withdrawal Fees", account_type=AccountType.EXPENSE),
        AccountCreate(name="Opening Balances", account_type=AccountType.EQUITY),
        AccountCreate(name="Realized Gain/Loss", account_type=AccountType.GAIN_LOSS),
        AccountCreate(name="Clearing", account_type=AccountType.CLEARING),
    ]
    existing_accounts = {(row.name, row.account_type, row.provider) for row in session.scalars(select(Account))}
    for item in requested_accounts:
        identity = (item.name.strip(), item.account_type.value, item.provider)
        if identity not in existing_accounts:
            session.add(
                Account(
                    name=identity[0],
                    account_type=identity[1],
                    channel_type=item.channel_type.value,
                    provider=identity[2],
                )
            )
    add_audit(session, "SETTINGS_INITIALIZED", details={"timezone": setting.timezone})
    session.commit()
    session.refresh(setting)
    return setting


@router.get("/settings", response_model=SettingsRead)
def get_settings(session: Session = Depends(get_session)) -> Setting:
    setting = session.get(Setting, "default")
    if setting is None:
        raise DomainError("onboarding has not been completed", 404)
    return setting


@router.get("/events", response_model=list[EventRead])
def list_events(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[EventRead]:
    statement = (
        select(TransactionEvent)
        .options(selectinload(TransactionEvent.entries).selectinload(LedgerEntry.account))
        .options(selectinload(TransactionEvent.entries).selectinload(LedgerEntry.asset))
        .order_by(TransactionEvent.occurred_at.desc())
        .limit(limit)
    )
    if status:
        statement = statement.where(TransactionEvent.status == status.upper())
    return [event_read(event) for event in session.scalars(statement)]


@router.get("/events/{event_id}", response_model=EventRead)
def event_detail(event_id: str, session: Session = Depends(get_session)) -> EventRead:
    return event_read(get_event(session, event_id))


@router.post("/events/drafts", response_model=EventRead, status_code=201)
def draft_event(payload: EventDraftCreate, session: Session = Depends(get_session)) -> EventRead:
    event = create_draft(session, payload)
    session.commit()
    return event_read(get_event(session, event.id))


@router.post("/events/manual", response_model=EventRead, status_code=201)
def manual_event(payload: ManualEventCreate, session: Session = Depends(get_session)) -> EventRead:
    event = create_manual_event(session, payload)
    session.commit()
    return event_read(get_event(session, event.id))


@router.post("/events/{event_id}/post", response_model=EventRead)
def post_draft(event_id: str, session: Session = Depends(get_session)) -> EventRead:
    event = post_event(session, get_event(session, event_id))
    session.commit()
    return event_read(get_event(session, event.id))


@router.post("/events/{event_id}/reverse", response_model=EventRead, status_code=201)
def reverse_posted(event_id: str, payload: ReverseCreate, session: Session = Depends(get_session)) -> EventRead:
    event = reverse_event(session, get_event(session, event_id), payload.reason)
    session.commit()
    return event_read(get_event(session, event.id))


@router.post("/trades", response_model=EventRead, status_code=201)
def post_trade(payload: TradeCreate, session: Session = Depends(get_session)) -> EventRead:
    event = create_trade(session, payload)
    session.commit()
    return event_read(get_event(session, event.id))


@router.post("/transfers", response_model=EventRead, status_code=201)
def post_transfer(payload: TransferCreate, session: Session = Depends(get_session)) -> EventRead:
    event = create_transfer(session, payload)
    session.commit()
    return event_read(get_event(session, event.id))


@router.post("/rates", status_code=201)
def create_rate(payload: RateCreate, session: Session = Depends(get_session)) -> dict[str, str]:
    if payload.base_asset_id == payload.quote_asset_id:
        raise DomainError("rate base and quote assets must differ")
    if session.get(Asset, payload.base_asset_id) is None or session.get(Asset, payload.quote_asset_id) is None:
        raise DomainError("rate assets do not exist")
    rate = RateSnapshot(
        base_asset_id=payload.base_asset_id,
        quote_asset_id=payload.quote_asset_id,
        rate=payload.rate,
        observed_at=utc_text(payload.observed_at),
        source=payload.source,
        rate_type=payload.rate_type.upper(),
        path=payload.path,
        confidence=payload.confidence,
    )
    session.add(rate)
    session.commit()
    return {"id": rate.id, "rate": rate.rate}


@router.get("/cost-lots", response_model=list[CostLotRead])
def list_cost_lots(
    asset_id: str | None = None,
    include_voided: bool = False,
    session: Session = Depends(get_session),
) -> list[dict]:
    statement = select(CostLot).order_by(CostLot.acquired_at, CostLot.id)
    if asset_id:
        statement = statement.where(CostLot.asset_id == asset_id)
    if not include_voided:
        statement = statement.where(CostLot.voided.is_(False))
    return [
        {
            "id": lot.id,
            "asset_id": lot.asset_id,
            "asset_symbol": lot.asset.symbol,
            "account_id": lot.account_id,
            "account_name": lot.account.name,
            "source_event_id": lot.source_event_id,
            "acquired_at": lot.acquired_at,
            "original_quantity": lot.original_quantity,
            "remaining_quantity": lot.remaining_quantity,
            "basis_myr": micros_to_myr(lot.basis_myr),
            "remaining_basis_myr": micros_to_myr(lot.remaining_basis_myr),
            "basis_status": lot.basis_status,
            "voided": lot.voided,
        }
        for lot in session.scalars(statement)
    ]


def card_read(session: Session, card: CardTransaction) -> dict:
    hold = session.scalar(select(CardHold).where(CardHold.card_transaction_id == card.id))
    return {
        "id": card.id,
        "event_id": card.event_id,
        "parent_card_transaction_id": card.parent_card_transaction_id,
        "original_transaction_id": card.original_transaction_id,
        "provider": card.provider,
        "external_id": card.external_id,
        "transaction_type": card.transaction_type,
        "merchant_name": card.merchant_name,
        "merchant_amount": card.merchant_amount,
        "merchant_asset_id": card.merchant_asset_id,
        "billing_amount": card.billing_amount,
        "billing_asset_id": card.billing_asset_id,
        "merchant_value_myr": micros_to_myr(card.merchant_value_myr),
        "status": card.status,
        "authorized_at": card.authorized_at,
        "settled_at": card.settled_at,
        "hold": {
            "account_id": hold.account_id,
            "asset_id": hold.asset_id,
            "amount": hold.amount,
            "value_myr": micros_to_myr(hold.value_myr),
            "status": hold.status,
        }
        if hold
        else None,
        "rewards": [
            {
                "id": reward.id,
                "asset_id": reward.asset_id,
                "amount": reward.amount,
                "status": reward.status,
                "value_myr": micros_to_myr(reward.value_myr) if reward.value_myr is not None else None,
            }
            for reward in card.rewards
        ],
    }


@router.get("/cards")
def list_cards(session: Session = Depends(get_session)) -> list[dict]:
    cards = session.scalars(select(CardTransaction).order_by(CardTransaction.created_at.desc())).all()
    return [card_read(session, card) for card in cards]


@router.post("/cards/authorizations", status_code=201)
def authorize_card(payload: CardAuthorizationCreate, session: Session = Depends(get_session)) -> dict:
    card = create_authorization(session, payload)
    session.commit()
    return card_read(session, card)


@router.post("/cards/{card_id}/reverse-authorization")
def reverse_card_authorization(card_id: str, session: Session = Depends(get_session)) -> dict:
    card = release_authorization(session, get_card(session, card_id))
    session.commit()
    return card_read(session, card)


@router.post("/cards/settlements", status_code=201)
def settle_card(payload: CardSettlementCreate, session: Session = Depends(get_session)) -> dict:
    card = create_settlement(session, payload)
    session.commit()
    return card_read(session, card)


@router.post("/cards/{card_id}/refunds", status_code=201)
def refund_card(card_id: str, payload: CardRefundCreate, session: Session = Depends(get_session)) -> dict:
    refund = create_refund(session, get_card(session, card_id), payload)
    session.commit()
    return card_read(session, refund)


@router.post("/cards/{card_id}/rewards", status_code=201)
def add_card_reward(card_id: str, payload: RewardCreate, session: Session = Depends(get_session)) -> dict:
    reward = create_reward(session, get_card(session, card_id), payload)
    session.commit()
    return {
        "id": reward.id,
        "card_transaction_id": reward.card_transaction_id,
        "asset_id": reward.asset_id,
        "amount": reward.amount,
        "status": reward.status,
    }


@router.post("/rewards/{reward_id}/credit")
def credit_card_reward(
    reward_id: str, payload: RewardCreditCreate, session: Session = Depends(get_session)
) -> dict:
    reward = session.get(Reward, reward_id)
    if reward is None:
        raise DomainError("reward not found", 404)
    credit_reward(session, reward, payload)
    session.commit()
    return {
        "id": reward.id,
        "event_id": reward.event_id,
        "status": reward.status,
        "value_myr": micros_to_myr(reward.value_myr or 0),
    }


@router.post("/rewards/{reward_id}/reverse")
def reverse_card_reward(reward_id: str, payload: ReverseCreate, session: Session = Depends(get_session)) -> dict:
    reward = session.get(Reward, reward_id)
    if reward is None:
        raise DomainError("reward not found", 404)
    reverse_reward(session, reward, payload.reason)
    session.commit()
    return {"id": reward.id, "status": reward.status}


def report_window(start: datetime | None, end: datetime | None) -> tuple[str | None, str | None]:
    return (utc_text(start) if start else None, utc_text(end) if end else None)


@router.get("/reports/net-worth")
def net_worth(
    as_of: datetime | None = None,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    _, end = report_window(None, as_of)
    totals = report_totals(session, end=end)
    return {"net_worth_myr": micros_to_myr(totals["assets"] - totals["liabilities"])}


@router.get("/reports/income-expense")
def income_expense(
    start: datetime | None = None,
    end: datetime | None = None,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    start_text, end_text = report_window(start, end)
    totals = report_totals(session, start_text, end_text)
    return {
        "income_myr": micros_to_myr(totals["income"]),
        "expense_myr": micros_to_myr(totals["expense"]),
        "net_income_myr": micros_to_myr(totals["income"] - totals["expense"]),
    }


@router.get("/reports/portfolio", response_model=list[PortfolioPositionRead])
def portfolio(
    as_of: datetime | None = None,
    session: Session = Depends(get_session),
) -> list[dict[str, str | bool | None]]:
    return portfolio_positions(session, utc_text(as_of) if as_of else None)


@router.get("/reports/fees")
def fees_report(
    start: datetime | None = None,
    end: datetime | None = None,
    session: Session = Depends(get_session),
) -> dict:
    start_text, end_text = report_window(start, end)
    return fee_report_data(session, start_text, end_text)


@router.get("/reports/fee-leakage")
def fee_leakage_report(
    start: datetime | None = None,
    end: datetime | None = None,
    session: Session = Depends(get_session),
) -> dict:
    start_text, end_text = report_window(start, end)
    return fee_leakage_data(session, start_text, end_text)


@router.get("/reports/card-costs")
def card_costs(session: Session = Depends(get_session)) -> list[dict]:
    return card_cost_report(session)


@router.get("/reports/summary", response_model=SummaryRead)
def summary(
    start: datetime | None = None,
    end: datetime | None = None,
    session: Session = Depends(get_session),
) -> SummaryRead:
    period_start, period_end = report_window(start, end)
    period = report_totals(session, period_start, period_end)
    lifetime = report_totals(session, end=period_end)
    channels = spending_by_channel(
        session,
        period_start or "0001-01-01T00:00:00+00:00",
        period_end or "9999-12-31T23:59:59+00:00",
    )
    gross_spending = sum(myr_to_micros(row["gross_spending_myr"]) for row in channels)
    net_spending = sum(myr_to_micros(row["net_spending_myr"]) for row in channels)
    return SummaryRead(
        net_worth_myr=micros_to_myr(lifetime["assets"] - lifetime["liabilities"]),
        income_myr=micros_to_myr(period["income"]),
        expense_myr=micros_to_myr(period["expense"]),
        gross_spending_myr=micros_to_myr(gross_spending),
        net_spending_myr=micros_to_myr(net_spending),
    )


@router.post("/journeys", status_code=201)
def create_funds_journey(payload: JourneyCreate, session: Session = Depends(get_session)) -> dict:
    journey = create_journey(session, payload)
    session.commit()
    return journey_report(session, journey.id)


@router.get("/journeys")
def list_funds_journeys(session: Session = Depends(get_session)) -> list[dict]:
    journey_ids = session.scalars(select(Journey.id).order_by(Journey.created_at.desc())).all()
    return [journey_report(session, journey_id) for journey_id in journey_ids]


@router.post("/journeys/{journey_id}/events", status_code=201)
def allocate_journey_event(
    journey_id: str,
    payload: JourneyEventCreate,
    session: Session = Depends(get_session),
) -> dict:
    journey = get_journey(session, journey_id)
    add_journey_event(session, journey, payload)
    session.commit()
    return journey_report(session, journey_id)


@router.get("/reports/journeys/{journey_id}")
def funds_journey_report(
    journey_id: str,
    as_of: datetime | None = None,
    session: Session = Depends(get_session),
) -> dict:
    return journey_report(session, journey_id, utc_text(as_of) if as_of else None)


@router.get("/reports/monthly")
def get_monthly_report(
    month: str = Query(pattern=r"^\d{4}-\d{2}$"),
    session: Session = Depends(get_session),
) -> dict:
    return monthly_report(session, month)


@router.post("/reports/monthly-snapshots", status_code=201)
def post_monthly_snapshot(
    month: str = Query(pattern=r"^\d{4}-\d{2}$"),
    session: Session = Depends(get_session),
) -> dict:
    snapshot = create_monthly_snapshot(session, month)
    session.commit()
    return snapshot


@router.get("/reports/monthly-snapshots")
def get_monthly_snapshots(session: Session = Depends(get_session)) -> list[dict[str, str]]:
    return list_snapshots(session)


@router.get("/reports/monthly-snapshots/{snapshot_id}")
def monthly_snapshot_detail(snapshot_id: str, session: Session = Depends(get_session)) -> dict:
    return get_snapshot(session, snapshot_id)


@router.post("/reports/channel-comparison")
def channel_comparison(payload: ChannelComparisonCreate) -> dict:
    return compare_channels(payload)
