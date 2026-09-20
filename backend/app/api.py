from datetime import date, datetime, time, timedelta
from pathlib import PurePosixPath
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, undefer
from starlette.datastructures import UploadFile

from app.cards import (
    available_account_balances,
    card_cost_report,
    create_authorization,
    create_refund,
    create_reward,
    create_settlement,
    credit_reward,
    derive_refund_expense_account,
    get_card,
    refund_summary,
    release_authorization,
    reverse_reward,
)
from app.cost_basis import portfolio_positions
from app.database import get_session
from app.enums import AccountChannel, AccountType, CategoryKind, EventStatus, EventType
from app.google_drive import (
    GoogleDriveError,
    begin_authorization,
    complete_authorization,
    get_backup_status,
    upload_database_backup,
)
from app.ledger import (
    DomainError,
    account_balances,
    add_audit,
    category_kind_for_account_types,
    create_manual_event,
    get_event,
    report_totals,
    reverse_event,
    utc_now_text,
    utc_text,
    validate_category_binding,
)
from app.models import (
    Account,
    Asset,
    CardHold,
    CardTransaction,
    Category,
    CostLot,
    EventReceipt,
    Journey,
    LedgerEntry,
    RateSnapshot,
    Reward,
    Setting,
    TransactionEvent,
)
from app.money import micros_to_myr, myr_to_micros
from app.recurring_expenses import (
    create_recurring_expense,
    list_occurrences,
    list_recurring_expenses,
    occurrence_read,
    record_recurring_expense,
    recurring_expense_read,
    skip_recurring_expense,
    update_recurring_expense,
)
from app.reporting import (
    add_journey_event,
    analytics_report,
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
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    ChannelComparisonCreate,
    CostLotRead,
    EventCategoryUpdate,
    EventRead,
    EventSearchPageRead,
    GoogleDriveBackupRead,
    GoogleDriveBackupStatusRead,
    JourneyCreate,
    JourneyEventCreate,
    ManualEventCreate,
    OnboardingCreate,
    PortfolioPositionRead,
    RateCreate,
    ReceiptRead,
    RecurringExpenseActionRead,
    RecurringExpenseCreate,
    RecurringExpenseListRead,
    RecurringExpenseOccurrenceRead,
    RecurringExpenseRead,
    RecurringExpenseRecordCreate,
    RecurringExpenseSkipCreate,
    RecurringExpenseUpdate,
    ReverseCreate,
    RewardCreate,
    RewardCreditCreate,
    SettingsRead,
    SummaryRead,
    TradeCreate,
    TransferCreate,
    normalize_category_name,
)
from app.trading import create_trade, create_transfer

router = APIRouter(prefix="/api")

MAX_RECEIPT_BYTES = 10 * 1024 * 1024
RECEIPT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def receipt_read(receipt: EventReceipt) -> ReceiptRead:
    return ReceiptRead(
        id=receipt.id,
        original_filename=receipt.original_filename,
        content_type=receipt.content_type,
        byte_size=receipt.byte_size,
        created_at=receipt.created_at,
        updated_at=receipt.updated_at,
    )


def event_read(event: TransactionEvent) -> EventRead:
    category = event.category_ref
    category_kind = category.kind if category else category_kind_for_account_types(
        [entry.account.account_type for entry in event.entries]
    )
    return EventRead(
        id=event.id,
        event_type=event.event_type,
        status=event.status,
        occurred_at=event.occurred_at,
        time_precision=event.time_precision,
        description=event.description,
        category=category.name if category else event.category,
        category_id=event.category_id,
        category_kind=category_kind,
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
        receipt=receipt_read(event.receipt) if event.receipt else None,
    )


def receipt_filename(filename: str | None) -> str:
    name = PurePosixPath((filename or "").replace("\\", "/")).name
    name = "".join(character for character in name if character >= " " and character not in {'"', "\r", "\n"})
    if not name:
        raise DomainError("receipt filename is required", 415)
    return name[:255]


def receipt_signature_matches(content_type: str, data: bytes) -> bool:
    if content_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"


@router.get("/assets", response_model=list[AssetRead])
def list_assets(session: Session = Depends(get_session)) -> list[Asset]:
    return list(session.scalars(select(Asset).order_by(Asset.symbol, Asset.chain)).all())


@router.get("/backups/google-drive/status", response_model=GoogleDriveBackupStatusRead)
def google_drive_backup_status() -> dict:
    return get_backup_status()


@router.get("/backups/google-drive/connect")
def connect_google_drive() -> RedirectResponse:
    try:
        return RedirectResponse(begin_authorization(), status_code=302)
    except GoogleDriveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


def oauth_callback_page(success: bool, message: str) -> str:
    title = "Google Drive connected" if success else "Google Drive connection failed"
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title></head>"
        f"<body><h1>{title}</h1><p>{message}</p>"
        "<p>You can close this window and return to CryptoSpend.</p></body></html>"
    )


@router.get("/backups/google-drive/oauth/callback", response_class=HTMLResponse)
def google_drive_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    try:
        complete_authorization(code, state, error)
    except GoogleDriveError as exc:
        return HTMLResponse(oauth_callback_page(False, exc.message), status_code=exc.status_code)
    return HTMLResponse(oauth_callback_page(True, "Google Drive is ready for database backups."))


@router.post("/backups/google-drive/upload", response_model=GoogleDriveBackupRead)
def upload_google_drive_backup() -> dict[str, str | None]:
    try:
        return upload_database_backup()
    except GoogleDriveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


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


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(
    kind: CategoryKind | None = None,
    include_inactive: bool = False,
    session: Session = Depends(get_session),
) -> list[Category]:
    statement = select(Category).order_by(Category.kind, Category.name, Category.id)
    if kind is not None:
        statement = statement.where(Category.kind == kind.value)
    if not include_inactive:
        statement = statement.where(Category.active.is_(True))
    return list(session.scalars(statement))


@router.post("/categories", response_model=CategoryRead, status_code=201)
def create_category(payload: CategoryCreate, session: Session = Depends(get_session)) -> Category:
    category = Category(
        name=payload.name,
        normalized_name=normalize_category_name(payload.name),
        kind=payload.kind.value,
    )
    session.add(category)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DomainError("a category with this name already exists for this type", 409) from exc
    return category


@router.patch("/categories/{category_id}", response_model=CategoryRead)
def update_category(category_id: str, payload: CategoryUpdate, session: Session = Depends(get_session)) -> Category:
    category = session.get(Category, category_id)
    if category is None:
        raise DomainError("category not found", 404)
    if payload.name is not None:
        duplicate = session.scalar(
            select(Category.id).where(
                Category.kind == category.kind,
                Category.normalized_name == normalize_category_name(payload.name),
                Category.id != category.id,
            )
        )
        if duplicate is not None:
            raise DomainError("a category with this name already exists for this type", 409)
        category.name = payload.name
        category.normalized_name = normalize_category_name(payload.name)
    if payload.active is not None:
        category.active = payload.active
    session.commit()
    return category


@router.get("/recurring-expenses", response_model=RecurringExpenseListRead)
def list_recurring_expense_templates(
    include_inactive: bool = False, session: Session = Depends(get_session)
) -> dict[str, object]:
    return list_recurring_expenses(session, include_inactive)


@router.post("/recurring-expenses", response_model=RecurringExpenseRead, status_code=201)
def create_recurring_expense_template(
    payload: RecurringExpenseCreate, session: Session = Depends(get_session)
) -> dict[str, object]:
    try:
        expense = create_recurring_expense(session, payload)
        session.commit()
    except DomainError:
        session.rollback()
        raise
    return recurring_expense_read(session, expense)


@router.patch("/recurring-expenses/{recurring_expense_id}", response_model=RecurringExpenseRead)
def update_recurring_expense_template(
    recurring_expense_id: str,
    payload: RecurringExpenseUpdate,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        expense = update_recurring_expense(session, recurring_expense_id, payload)
        session.commit()
    except DomainError:
        session.rollback()
        raise
    return recurring_expense_read(session, expense)


@router.post(
    "/recurring-expenses/{recurring_expense_id}/record",
    response_model=RecurringExpenseActionRead,
    status_code=201,
)
def record_recurring_expense_payment(
    recurring_expense_id: str,
    payload: RecurringExpenseRecordCreate,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        expense, occurrence = record_recurring_expense(session, recurring_expense_id, payload)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DomainError("this occurrence has already been handled", 409) from exc
    except DomainError:
        session.rollback()
        raise
    return {
        "occurrence": occurrence_read(session, occurrence.id),
        "recurring_expense": recurring_expense_read(session, expense),
    }


@router.post(
    "/recurring-expenses/{recurring_expense_id}/skip",
    response_model=RecurringExpenseActionRead,
    status_code=201,
)
def skip_recurring_expense_occurrence(
    recurring_expense_id: str,
    payload: RecurringExpenseSkipCreate,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        expense, occurrence = skip_recurring_expense(session, recurring_expense_id, payload)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DomainError("this occurrence has already been handled", 409) from exc
    except DomainError:
        session.rollback()
        raise
    return {
        "occurrence": occurrence_read(session, occurrence.id),
        "recurring_expense": recurring_expense_read(session, expense),
    }


@router.get(
    "/recurring-expenses/{recurring_expense_id}/occurrences",
    response_model=list[RecurringExpenseOccurrenceRead],
)
def list_recurring_expense_occurrences(
    recurring_expense_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    return list_occurrences(session, recurring_expense_id, limit)


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
        .options(selectinload(TransactionEvent.category_ref))
        .options(selectinload(TransactionEvent.receipt))
        .order_by(TransactionEvent.occurred_at.desc())
        .limit(limit)
    )
    if status:
        statement = statement.where(TransactionEvent.status == status.upper())
    return [event_read(event) for event in session.scalars(statement)]


def event_search_conditions(
    session: Session,
    query: str | None,
    event_type: EventType | None,
    status: EventStatus | None,
    category_id: str | None,
    from_date: date | None,
    to_date: date | None,
) -> list[object]:
    setting = session.get(Setting, "default")
    timezone = setting.timezone if setting else "Asia/Kuala_Lumpur"
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise DomainError(f"configured timezone is unavailable: {timezone}") from exc

    conditions: list[object] = []
    if query and (clean_query := query.strip()):
        pattern = f"%{clean_query}%"
        conditions.append(
            or_(
                TransactionEvent.id.ilike(pattern),
                TransactionEvent.description.ilike(pattern),
                TransactionEvent.event_type.ilike(pattern),
                func.replace(TransactionEvent.event_type, "_", " ").ilike(pattern),
                TransactionEvent.category.ilike(pattern),
                TransactionEvent.source.ilike(pattern),
                TransactionEvent.external_id.ilike(pattern),
                Category.name.ilike(pattern),
            )
        )
    if event_type:
        conditions.append(TransactionEvent.event_type == event_type.value)
    if status:
        conditions.append(TransactionEvent.status == status.value)
    if category_id:
        if category_id.casefold() == "uncategorized":
            conditions.append(TransactionEvent.category_id.is_(None))
        else:
            conditions.append(TransactionEvent.category_id == category_id)

    if from_date:
        start = datetime.combine(from_date, time.min, tzinfo=zone)
        conditions.append(TransactionEvent.occurred_at >= utc_text(start))
    if to_date:
        end = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=zone)
        conditions.append(TransactionEvent.occurred_at < utc_text(end))
    if from_date and to_date and from_date > to_date:
        raise DomainError("from_date must be on or before to_date")
    return conditions


@router.get("/events/search", response_model=EventSearchPageRead)
def search_events(
    q: str | None = Query(default=None, max_length=200),
    event_type: EventType | None = None,
    status: EventStatus | None = None,
    category_id: str | None = Query(default=None, max_length=64),
    from_date: date | None = None,
    to_date: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    conditions = event_search_conditions(session, q, event_type, status, category_id, from_date, to_date)
    join_category = TransactionEvent.category_id == Category.id
    total = session.scalar(
        select(func.count(TransactionEvent.id))
        .select_from(TransactionEvent)
        .outerjoin(Category, join_category)
        .where(*conditions)
    ) or 0
    statement = (
        select(TransactionEvent)
        .outerjoin(Category, join_category)
        .options(selectinload(TransactionEvent.entries).selectinload(LedgerEntry.account))
        .options(selectinload(TransactionEvent.entries).selectinload(LedgerEntry.asset))
        .options(selectinload(TransactionEvent.category_ref))
        .options(selectinload(TransactionEvent.receipt))
        .where(*conditions)
        .order_by(TransactionEvent.occurred_at.desc(), TransactionEvent.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [event_read(event) for event in session.scalars(statement)]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/events/drafts", include_in_schema=False)
def removed_draft_event() -> None:
    raise HTTPException(status_code=404, detail="generic draft events are not supported")


@router.get("/events/{event_id}", response_model=EventRead)
def event_detail(event_id: str, session: Session = Depends(get_session)) -> EventRead:
    return event_read(get_event(session, event_id))


@router.put("/events/{event_id}/receipt", response_model=ReceiptRead)
async def upload_event_receipt(
    event_id: str, request: Request, session: Session = Depends(get_session)
) -> ReceiptRead:
    event = get_event(session, event_id)
    form = await request.form()
    uploaded = form.get("file")
    if not isinstance(uploaded, UploadFile):
        raise DomainError("multipart field 'file' is required", 422)

    filename = receipt_filename(uploaded.filename)
    content_type = (uploaded.content_type or "").lower()
    expected_type = RECEIPT_TYPES.get(PurePosixPath(filename).suffix.lower())
    if content_type not in set(RECEIPT_TYPES.values()) or expected_type != content_type:
        raise DomainError("receipt must be a JPEG, PNG, or WebP image", 415)

    chunks: list[bytes] = []
    byte_size = 0
    while True:
        chunk = await uploaded.read(1024 * 1024)
        if not chunk:
            break
        byte_size += len(chunk)
        if byte_size > MAX_RECEIPT_BYTES:
            raise DomainError("receipt exceeds the 10 MiB limit", 413)
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise DomainError("receipt file must not be empty")
    if not receipt_signature_matches(content_type, data):
        raise DomainError("receipt content does not match its declared image type", 415)

    receipt = event.receipt
    action = "RECEIPT_REPLACED" if receipt else "RECEIPT_ATTACHED"
    if receipt is None:
        receipt = EventReceipt(event_id=event.id)
        session.add(receipt)
    receipt.original_filename = filename
    receipt.content_type = content_type
    receipt.byte_size = byte_size
    receipt.data = data
    receipt.updated_at = utc_now_text()
    session.flush()
    add_audit(
        session,
        action,
        event.id,
        {"original_filename": filename, "content_type": content_type, "byte_size": byte_size},
    )
    session.commit()
    return receipt_read(receipt)


@router.get("/events/{event_id}/receipt")
def download_event_receipt(event_id: str, session: Session = Depends(get_session)) -> Response:
    receipt = session.scalar(
        select(EventReceipt)
        .options(undefer(EventReceipt.data))
        .where(EventReceipt.event_id == event_id)
    )
    if receipt is None:
        raise DomainError("receipt not found", 404)
    return Response(
        content=receipt.data,
        media_type=receipt.content_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(receipt.original_filename, safe='')}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/events/{event_id}/receipt", status_code=204)
def delete_event_receipt(event_id: str, session: Session = Depends(get_session)) -> Response:
    receipt = session.scalar(select(EventReceipt).where(EventReceipt.event_id == event_id))
    if receipt is None:
        raise DomainError("receipt not found", 404)
    session.delete(receipt)
    add_audit(session, "RECEIPT_REMOVED", event_id)
    session.commit()
    return Response(status_code=204)


@router.post("/events/manual", response_model=EventRead, status_code=201)
def manual_event(payload: ManualEventCreate, session: Session = Depends(get_session)) -> EventRead:
    event = create_manual_event(session, payload)
    session.commit()
    return event_read(get_event(session, event.id))


@router.post("/events/{event_id}/reverse", response_model=EventRead, status_code=201)
def reverse_posted(event_id: str, payload: ReverseCreate, session: Session = Depends(get_session)) -> EventRead:
    event = reverse_event(session, get_event(session, event_id), payload.reason)
    session.commit()
    return event_read(get_event(session, event.id))


@router.patch("/events/{event_id}/category", response_model=EventRead)
def update_event_category(
    event_id: str, payload: EventCategoryUpdate, session: Session = Depends(get_session)
) -> EventRead:
    event = get_event(session, event_id)
    account_types = [entry.account.account_type for entry in event.entries]
    category = validate_category_binding(
        session,
        payload.category_id,
        event.event_type,
        account_types,
    )
    if category is None:
        raise DomainError("category_id is required")
    previous_id = event.category_id
    event.category_id = category.id
    event.category = category.name
    event.category_ref = category
    add_audit(
        session,
        "EVENT_CATEGORY_CHANGED",
        event.id,
        {"old_category_id": previous_id, "new_category_id": category.id},
    )
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
    summary = refund_summary(session, card) if card.transaction_type == "PURCHASE" else None
    expense = derive_refund_expense_account(session, card) if summary is not None else None
    return {
        "id": card.id,
        "event_id": card.event_id,
        "parent_card_transaction_id": card.parent_card_transaction_id,
        "original_transaction_id": card.original_transaction_id,
        "provider": card.provider,
        "provider_account_id": card.provider_account_id,
        "external_id": card.external_id,
        "transaction_type": card.transaction_type,
        "card_account_id": card.card_account_id,
        "merchant_name": card.merchant_name,
        "merchant_country": card.merchant_country,
        "merchant_amount": card.merchant_amount,
        "merchant_asset_id": card.merchant_asset_id,
        "billing_amount": card.billing_amount,
        "billing_asset_id": card.billing_asset_id,
        "merchant_value_myr": micros_to_myr(card.merchant_value_myr),
        "category_id": card.event.category_id if card.event else None,
        "expense_account_id": expense.id if expense else None,
        "refunded_value_myr": micros_to_myr(int(summary["refunded_transaction_value_myr"]))
        if summary is not None
        else "0",
        "refundable_remaining_myr": micros_to_myr(int(summary["refundable_remaining_myr"]))
        if summary is not None
        else None,
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


@router.get("/reports/analytics")
def get_analytics_report(
    period: str,
    anchor: str | None = None,
    session: Session = Depends(get_session),
) -> dict:
    return analytics_report(session, period, anchor)


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
