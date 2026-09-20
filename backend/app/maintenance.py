import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config

from app.database import BACKEND_DIR, DEFAULT_DATABASE_PATH
from app.enums import CardStatus
from app.money import canonical_decimal, micros_to_myr, myr_to_micros, parse_decimal


def _read_only_connection(database_path: Path) -> sqlite3.Connection:
    if not database_path.exists():
        raise FileNotFoundError(database_path)
    uri = f"file:{database_path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _issue(
    code: str,
    *,
    event_id: str | None = None,
    card_id: str | None = None,
    occurred_at: str | None = None,
    asset_id: str | None = None,
    asset_symbol: str | None = None,
    account_id: str | None = None,
    account_name: str | None = None,
    quantity: str | None = None,
    value_myr: str | None = None,
    reason: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "event_id": event_id,
        "card_id": card_id,
        "occurred_at": occurred_at,
        "asset_id": asset_id,
        "asset_symbol": asset_symbol,
        "account_id": account_id,
        "account_name": account_name,
        "quantity": quantity,
        "value_myr": value_myr,
        "reason": reason,
    }


def _is_myr(asset: sqlite3.Row) -> bool:
    return asset["symbol"].upper() == "MYR" and asset["chain"] is None


def _active_projection_totals(connection: sqlite3.Connection) -> dict[tuple[str, str, str], Decimal]:
    totals: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    for row in connection.execute(
        """
        SELECT ld.event_id, cl.account_id, cl.asset_id, ld.quantity
        FROM lot_disposals AS ld
        JOIN cost_lots AS cl ON cl.id = ld.cost_lot_id
        WHERE ld.reversed = 0
        """
    ):
        totals[(row["event_id"], row["account_id"], row["asset_id"])] += parse_decimal(row["quantity"])
    for row in connection.execute(
        """
        SELECT lt.event_id, source.account_id, source.asset_id, lt.quantity
        FROM lot_transfers AS lt
        JOIN cost_lots AS source ON source.id = lt.source_lot_id
        WHERE lt.reversed = 0
        """
    ):
        totals[(row["event_id"], row["account_id"], row["asset_id"])] += parse_decimal(row["quantity"])
    return totals


def _audit_unprojected_reductions(connection: sqlite3.Connection, issues: list[dict[str, Any]]) -> None:
    assets = {row["id"]: row for row in connection.execute("SELECT id, symbol, chain FROM assets")}
    projections = _active_projection_totals(connection)
    reductions: dict[tuple[str, str, str], tuple[sqlite3.Row, Decimal, int]] = {}
    for row in connection.execute(
        """
        SELECT e.id AS event_id, e.event_type, e.reverses_event_id, e.occurred_at,
               le.account_id, le.asset_id, le.quantity, le.book_amount_myr,
               a.name AS account_name, a.account_type, ass.symbol, ass.chain
        FROM ledger_entries AS le
        JOIN transaction_events AS e ON e.id = le.event_id
        JOIN accounts AS a ON a.id = le.account_id
        JOIN assets AS ass ON ass.id = le.asset_id
        WHERE e.status = 'POSTED'
          AND le.direction = 'CREDIT'
          AND a.account_type = 'ASSET'
        """
    ):
        asset = assets[row["asset_id"]]
        if _is_myr(asset) or row["event_type"] == "REVERSAL" or row["reverses_event_id"] is not None:
            continue
        key = (row["event_id"], row["account_id"], row["asset_id"])
        previous = reductions.get(key)
        if previous is None:
            reductions[key] = (row, parse_decimal(row["quantity"]), row["book_amount_myr"])
        else:
            reductions[key] = (
                previous[0],
                previous[1] + parse_decimal(row["quantity"]),
                previous[2] + row["book_amount_myr"],
            )

    for (event_id, account_id, asset_id), (row, quantity, book_amount) in reductions.items():
        covered = projections.get((event_id, account_id, asset_id), Decimal(0))
        if covered != quantity:
            issues.append(
                _issue(
                    "AUD-01",
                    event_id=event_id,
                    occurred_at=row["occurred_at"],
                    asset_id=asset_id,
                    asset_symbol=row["symbol"],
                    account_id=account_id,
                    account_name=row["account_name"],
                    quantity=canonical_decimal(quantity),
                    value_myr=micros_to_myr(book_amount),
                    reason=(
                        f"non-MYR ASSET credit has {quantity} quantity but active disposal/transfer projection "
                        f"covers {covered}"
                    ),
                )
            )


def _audit_missing_acquisition_lots(connection: sqlite3.Connection, issues: list[dict[str, Any]]) -> None:
    lots: dict[tuple[str, str, str], tuple[Decimal, int]] = defaultdict(lambda: (Decimal(0), 0))
    for row in connection.execute(
        """
        SELECT source_event_id, account_id, asset_id, original_quantity, basis_myr
        FROM cost_lots
        WHERE voided = 0 AND parent_lot_id IS NULL
        """
    ):
        key = (row["source_event_id"], row["account_id"], row["asset_id"])
        quantity, basis = lots[key]
        lots[key] = (quantity + parse_decimal(row["original_quantity"]), basis + row["basis_myr"])

    for row in connection.execute(
        """
        SELECT e.id AS event_id, e.occurred_at, le.account_id, le.asset_id,
               le.quantity, le.book_amount_myr, a.name AS account_name, ass.symbol
        FROM ledger_entries AS le
        JOIN transaction_events AS e ON e.id = le.event_id
        JOIN accounts AS a ON a.id = le.account_id
        JOIN assets AS ass ON ass.id = le.asset_id
        WHERE e.status = 'POSTED'
          AND e.event_type IN ('OPENING_BALANCE', 'SALARY', 'INCOME', 'REWARD')
          AND le.direction = 'DEBIT'
          AND a.account_type = 'ASSET'
        """
    ):
        quantity, basis = lots.get((row["event_id"], row["account_id"], row["asset_id"]), (Decimal(0), 0))
        expected_quantity = parse_decimal(row["quantity"])
        if quantity != expected_quantity or basis != row["book_amount_myr"]:
            issues.append(
                _issue(
                    "AUD-02",
                    event_id=row["event_id"],
                    occurred_at=row["occurred_at"],
                    asset_id=row["asset_id"],
                    asset_symbol=row["symbol"],
                    account_id=row["account_id"],
                    account_name=row["account_name"],
                    quantity=row["quantity"],
                    value_myr=micros_to_myr(row["book_amount_myr"]),
                    reason=(
                        f"active acquisition lots total {quantity} quantity and {micros_to_myr(basis)} MYR "
                        f"instead of {expected_quantity} and {micros_to_myr(row['book_amount_myr'])} MYR"
                    ),
                )
            )


def _audit_lot_ledger_quantities(connection: sqlite3.Connection, issues: list[dict[str, Any]]) -> None:
    assets = {row["id"]: row for row in connection.execute("SELECT id, symbol, chain FROM assets")}
    lots: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for row in connection.execute(
        "SELECT account_id, asset_id, remaining_quantity FROM cost_lots WHERE voided = 0"
    ):
        asset = assets[row["asset_id"]]
        if not _is_myr(asset):
            lots[(row["account_id"], row["asset_id"])] += parse_decimal(row["remaining_quantity"])

    ledger: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    latest_event: dict[tuple[str, str], tuple[str, str]] = {}
    for row in connection.execute(
        """
        SELECT e.id AS event_id, e.occurred_at, le.account_id, le.asset_id,
               le.direction, le.quantity
        FROM ledger_entries AS le
        JOIN transaction_events AS e ON e.id = le.event_id
        JOIN accounts AS a ON a.id = le.account_id
        JOIN assets AS ass ON ass.id = le.asset_id
        WHERE e.status = 'POSTED' AND a.account_type = 'ASSET'
        """
    ):
        if _is_myr(assets[row["asset_id"]]):
            continue
        sign = Decimal(1) if row["direction"] == "DEBIT" else Decimal(-1)
        key = (row["account_id"], row["asset_id"])
        ledger[key] += parse_decimal(row["quantity"]) * sign
        if key not in latest_event or row["occurred_at"] > latest_event[key][0]:
            latest_event[key] = (row["occurred_at"], row["event_id"])

    accounts = {row["id"]: row for row in connection.execute("SELECT id, name FROM accounts")}
    keys = set(lots) | set(ledger)
    for account_id, asset_id in sorted(keys):
        lot_quantity = lots.get((account_id, asset_id), Decimal(0))
        ledger_quantity = ledger.get((account_id, asset_id), Decimal(0))
        if lot_quantity == ledger_quantity:
            continue
        occurred_at, event_id = latest_event.get((account_id, asset_id), (None, None))
        asset = assets[asset_id]
        issues.append(
            _issue(
                "AUD-03",
                event_id=event_id,
                occurred_at=occurred_at,
                asset_id=asset_id,
                asset_symbol=asset["symbol"],
                account_id=account_id,
                account_name=accounts[account_id]["name"],
                quantity="0" if lot_quantity == 0 else str(lot_quantity),
                value_myr=None,
                reason=f"active lot quantity is {lot_quantity}, effective ledger quantity is {ledger_quantity}",
            )
        )


def _audit_valuation_rates(connection: sqlite3.Connection, issues: list[dict[str, Any]]) -> None:
    for row in connection.execute(
        """
        SELECT e.id AS event_id, e.occurred_at, le.account_id, le.asset_id,
               le.quantity, le.book_amount_myr, le.valuation_rate,
               a.name AS account_name, ass.symbol
        FROM ledger_entries AS le
        JOIN transaction_events AS e ON e.id = le.event_id
        JOIN accounts AS a ON a.id = le.account_id
        JOIN assets AS ass ON ass.id = le.asset_id
        WHERE le.valuation_rate IS NOT NULL
          AND le.direction = 'DEBIT'
          AND a.account_type = 'ASSET'
        """
    ):
        try:
            expected = myr_to_micros(parse_decimal(row["quantity"]) * parse_decimal(row["valuation_rate"]))
            rate_error = None
        except ValueError as exc:
            expected = None
            rate_error = str(exc)
        if expected == row["book_amount_myr"] and rate_error is None:
            continue
        reason = (
            f"quantity * valuation rate rounds to {micros_to_myr(expected)} MYR"
            if expected is not None
            else rate_error
        )
        issues.append(
            _issue(
                "AUD-04",
                event_id=row["event_id"],
                occurred_at=row["occurred_at"],
                asset_id=row["asset_id"],
                asset_symbol=row["symbol"],
                account_id=row["account_id"],
                account_name=row["account_name"],
                quantity=row["quantity"],
                value_myr=micros_to_myr(row["book_amount_myr"]),
                reason=f"{reason}; stored value is {micros_to_myr(row['book_amount_myr'])} MYR",
            )
        )


def _normalize_merchant(value: str | None) -> str | None:
    return " ".join(value.strip().split()).casefold() if value is not None else None


def _audit_authorization_identity(connection: sqlite3.Connection, issues: list[dict[str, Any]]) -> None:
    fields = (
        ("provider", lambda value: value.strip().upper()),
        ("provider_account_id", lambda value: value),
        ("card_account_id", lambda value: value),
        ("merchant_name", _normalize_merchant),
        ("merchant_country", lambda value: value.upper() if value is not None else None),
        ("merchant_asset_id", lambda value: value),
        ("billing_asset_id", lambda value: value),
    )
    for row in connection.execute(
        """
        SELECT child.id AS card_id, child.event_id, child.settled_at, child.merchant_amount,
               child.merchant_value_myr, child.merchant_asset_id, child.card_account_id,
               child.provider, child.provider_account_id, child.merchant_name,
               child.merchant_country, child.billing_asset_id,
               auth.provider AS auth_provider, auth.provider_account_id AS auth_provider_account_id,
               auth.card_account_id AS auth_card_account_id, auth.merchant_name AS auth_merchant_name,
               auth.merchant_country AS auth_merchant_country, auth.merchant_asset_id AS auth_merchant_asset_id,
               auth.billing_asset_id AS auth_billing_asset_id
        FROM card_transactions AS child
        JOIN card_transactions AS auth ON auth.id = child.parent_card_transaction_id
        WHERE child.transaction_type = 'PURCHASE'
        """
    ):
        mismatches = [
            name
            for name, normalize in fields
            if normalize(row[name]) != normalize(row[f"auth_{name}"])
        ]
        if not mismatches:
            continue
        issues.append(
            _issue(
                "AUD-05",
                event_id=row["event_id"],
                card_id=row["card_id"],
                occurred_at=row["settled_at"],
                asset_id=row["merchant_asset_id"],
                account_id=row["card_account_id"],
                quantity=row["merchant_amount"],
                value_myr=micros_to_myr(row["merchant_value_myr"]),
                reason=f"authorization identity mismatch in {', '.join(mismatches)}",
            )
        )


def _card_refund_totals(connection: sqlite3.Connection) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for row in connection.execute(
        """
        SELECT original_transaction_id, merchant_value_myr
        FROM card_transactions
        WHERE transaction_type = 'REFUND'
          AND reversed = 0
          AND original_transaction_id IS NOT NULL
        """
    ):
        totals[row["original_transaction_id"]] += row["merchant_value_myr"]
    return totals


def _audit_refunds(connection: sqlite3.Connection, issues: list[dict[str, Any]]) -> None:
    refund_totals = _card_refund_totals(connection)
    for row in connection.execute(
        """
        SELECT id AS card_id, event_id, settled_at, merchant_asset_id, card_account_id,
               merchant_amount, merchant_value_myr, status, reversed
        FROM card_transactions
        WHERE transaction_type = 'PURCHASE'
        """
    ):
        if row["reversed"]:
            continue
        refunded = refund_totals.get(row["card_id"], 0)
        if refunded > row["merchant_value_myr"]:
            issues.append(
                _issue(
                    "AUD-06",
                    event_id=row["event_id"],
                    card_id=row["card_id"],
                    occurred_at=row["settled_at"],
                    asset_id=row["merchant_asset_id"],
                    account_id=row["card_account_id"],
                    quantity=row["merchant_amount"],
                    value_myr=micros_to_myr(refunded),
                    reason=(
                        f"active refund transaction value {micros_to_myr(refunded)} MYR exceeds purchase value "
                        f"{micros_to_myr(row['merchant_value_myr'])} MYR"
                    ),
                )
            )
        if refunded == 0:
            expected_status = CardStatus.SETTLED.value
        elif refunded == row["merchant_value_myr"]:
            expected_status = CardStatus.REFUNDED.value
        else:
            expected_status = CardStatus.PARTIALLY_REFUNDED.value
        if row["status"] != expected_status:
            issues.append(
                _issue(
                    "AUD-07",
                    event_id=row["event_id"],
                    card_id=row["card_id"],
                    occurred_at=row["settled_at"],
                    asset_id=row["merchant_asset_id"],
                    account_id=row["card_account_id"],
                    quantity=row["merchant_amount"],
                    value_myr=micros_to_myr(row["merchant_value_myr"]),
                    reason=(
                        f"stored status {row['status']} should be {expected_status} for "
                        f"{micros_to_myr(refunded)} MYR refunded"
                    ),
                )
            )


def _audit_partial_captures(connection: sqlite3.Connection, issues: list[dict[str, Any]]) -> None:
    child_counts: dict[str, int] = defaultdict(int)
    for row in connection.execute(
        """
        SELECT parent_card_transaction_id, COUNT(*) AS child_count
        FROM card_transactions
        WHERE transaction_type = 'PURCHASE' AND reversed = 0
          AND parent_card_transaction_id IS NOT NULL
        GROUP BY parent_card_transaction_id
        """
    ):
        child_counts[row["parent_card_transaction_id"]] = row["child_count"]
    for row in connection.execute(
        """
        SELECT id AS card_id, event_id, authorized_at, merchant_asset_id, card_account_id,
               merchant_amount, merchant_value_myr, status
        FROM card_transactions
        WHERE transaction_type = 'AUTHORIZATION'
        """
    ):
        reasons: list[str] = []
        if row["status"] == "PARTIALLY_SETTLED":
            reasons.append("status is PARTIALLY_SETTLED")
        if child_counts.get(row["card_id"], 0) > 1:
            reasons.append(f"has {child_counts[row['card_id']]} active child purchases")
        if not reasons:
            continue
        issues.append(
            _issue(
                "AUD-08",
                event_id=row["event_id"],
                card_id=row["card_id"],
                occurred_at=row["authorized_at"],
                asset_id=row["merchant_asset_id"],
                account_id=row["card_account_id"],
                quantity=row["merchant_amount"],
                value_myr=micros_to_myr(row["merchant_value_myr"]),
                reason="; ".join(reasons),
            )
        )


def audit_integrity(database_path: Path = DEFAULT_DATABASE_PATH) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    with _read_only_connection(database_path) as connection:
        _audit_unprojected_reductions(connection, issues)
        _audit_missing_acquisition_lots(connection, issues)
        _audit_lot_ledger_quantities(connection, issues)
        _audit_valuation_rates(connection, issues)
        _audit_authorization_identity(connection, issues)
        _audit_refunds(connection, issues)
        _audit_partial_captures(connection, issues)
    issues.sort(key=lambda item: (item["code"], item["occurred_at"] or "", item["event_id"] or item["card_id"] or ""))
    return {
        "schema_version": 1,
        "database": str(database_path),
        "generated_at": datetime.now(UTC).isoformat(),
        "issue_count": len(issues),
        "issues": issues,
    }


def write_audit_json(report: dict[str, Any], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def print_audit_summary(report: dict[str, Any]) -> None:
    print(f"Accounting integrity audit: {report['issue_count']} issue(s)")
    if not report["issues"]:
        print("No integrity issues found.")
        return
    by_code: dict[str, int] = defaultdict(int)
    for issue in report["issues"]:
        by_code[issue["code"]] += 1
        identity = issue["event_id"] or issue["card_id"] or "unknown-record"
        print(f"{issue['code']} {identity} {issue['occurred_at'] or 'time-unknown'}: {issue['reason']}")
    print("Summary: " + ", ".join(f"{code}={count}" for code, count in sorted(by_code.items())))


def backup_database(source: Path, destination: Path) -> Path:
    if not source.exists():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(source)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
        result = destination_connection.execute("PRAGMA integrity_check").fetchone()
        if result != ("ok",):
            raise RuntimeError("backup integrity check failed")
    finally:
        destination_connection.close()
        source_connection.close()
    return destination


def restore_database(source: Path, destination: Path) -> Path:
    if not source.exists():
        raise FileNotFoundError(source)
    with sqlite3.connect(source) as source_connection:
        if source_connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise RuntimeError("source backup integrity check failed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_connection, sqlite3.connect(destination) as destination_connection:
        source_connection.backup(destination_connection)
    return destination


def migrate_database(database_path: Path = DEFAULT_DATABASE_PATH) -> Path | None:
    backup_path = None
    if database_path.exists() and database_path.stat().st_size:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_path = backup_database(database_path, BACKEND_DIR / "data" / "backups" / f"pre-migration-{stamp}.db")

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    command.upgrade(config, "head")
    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser(description="CryptoSpend database maintenance")
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("destination", type=Path)
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("source", type=Path)
    migrate_parser = subparsers.add_parser("migrate")
    migrate_parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    audit_parser = subparsers.add_parser("audit-integrity")
    audit_parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    audit_parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    try:
        if args.command == "backup":
            backup_database(DEFAULT_DATABASE_PATH, args.destination)
        elif args.command == "restore":
            restore_database(args.source, DEFAULT_DATABASE_PATH)
        elif args.command == "audit-integrity":
            report = audit_integrity(args.database)
            if args.json:
                write_audit_json(report, args.json)
                print(f"Audit JSON: {args.json}")
            print_audit_summary(report)
            return 2 if report["issue_count"] else 0
        else:
            migrate_database(args.database)
    except (OSError, RuntimeError, sqlite3.Error, ValueError) as exc:
        print(f"maintenance error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
