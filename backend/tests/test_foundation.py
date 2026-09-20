import hashlib
import json
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import create_sqlite_engine
from app.main import app
from app.maintenance import audit_integrity, backup_database, main, migrate_database, restore_database, write_audit_json
from app.money import canonical_decimal, micros_to_myr, myr_to_micros, parse_decimal


def _insert_event(connection: sqlite3.Connection, event_id: str, event_type: str, occurred_at: str) -> None:
    connection.execute(
        """
        INSERT INTO transaction_events
            (id, event_type, status, occurred_at, time_precision, description, source, created_at, posted_at)
        VALUES (?, ?, 'POSTED', ?, 'EXACT', '', 'SYSTEM', ?, ?)
        """,
        (event_id, event_type, occurred_at, occurred_at, occurred_at),
    )


def _insert_entry(
    connection: sqlite3.Connection,
    entry_id: str,
    event_id: str,
    account_id: str,
    asset_id: str,
    direction: str,
    quantity: str,
    book_amount_myr: int,
    valuation_rate: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO ledger_entries
            (id, event_id, account_id, asset_id, direction, quantity, book_amount_myr, valuation_rate)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (entry_id, event_id, account_id, asset_id, direction, quantity, book_amount_myr, valuation_rate),
    )


def _insert_card(connection: sqlite3.Connection, **overrides: object) -> None:
    values: dict[str, object] = {
        "id": "card",
        "event_id": None,
        "parent_card_transaction_id": None,
        "original_transaction_id": None,
        "provider": "PROVIDER",
        "provider_account_id": "provider-account",
        "external_id": None,
        "transaction_type": "PURCHASE",
        "card_account_id": "wallet",
        "merchant_name": "Shop",
        "merchant_country": "MY",
        "merchant_asset_id": "myr",
        "merchant_amount": "100",
        "billing_asset_id": "usdt",
        "billing_amount": "23.5",
        "merchant_value_myr": 100_000_000,
        "funding_value_myr": 100_000_000,
        "separate_fee_value_myr": 0,
        "gross_economic_cost_myr": 100_000_000,
        "net_economic_cost_myr": 100_000_000,
        "total_leakage_myr": 0,
        "breakdown_confidence": "MISSING_INPUT",
        "status": "SETTLED",
        "authorized_at": "2026-09-21T00:00:00+00:00",
        "settled_at": "2026-09-21T00:01:00+00:00",
        "created_at": "2026-09-21T00:01:00+00:00",
        "reversed": 0,
    }
    values.update(overrides)
    fields = list(values)
    placeholders = ", ".join("?" for _ in fields)
    connection.execute(
        f"INSERT INTO card_transactions ({', '.join(fields)}) VALUES ({placeholders})",
        tuple(values[field] for field in fields),
    )


def _prepare_audit_database(path: Path, *, clean: bool = False) -> None:
    migrate_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO assets (id, symbol, name, decimals, active, created_at) "
            "VALUES ('myr', 'MYR', 'Ringgit', 2, 1, '2026-09-21T00:00:00+00:00')"
        )
        connection.execute(
            "INSERT INTO assets (id, symbol, name, decimals, active, created_at) "
            "VALUES ('usdt', 'USDT', 'Tether', 8, 1, '2026-09-21T00:00:00+00:00')"
        )
        connection.execute(
            "INSERT INTO accounts (id, name, account_type, closed, created_at) "
            "VALUES ('wallet', 'Wallet', 'ASSET', 0, '2026-09-21T00:00:00+00:00')"
        )
        connection.execute(
            "INSERT INTO accounts (id, name, account_type, closed, created_at) "
            "VALUES ('income', 'Income', 'INCOME', 0, '2026-09-21T00:00:00+00:00')"
        )
        if clean:
            _insert_event(connection, "clean-acq", "SALARY", "2026-09-21T00:00:00+00:00")
            _insert_entry(
                connection,
                "clean-debit",
                "clean-acq",
                "wallet",
                "usdt",
                "DEBIT",
                "10",
                42_500_000,
                "4.25",
            )
            _insert_entry(
                connection,
                "clean-credit",
                "clean-acq",
                "income",
                "usdt",
                "CREDIT",
                "10",
                42_500_000,
                "4.25",
            )
            connection.execute(
                """
                INSERT INTO cost_lots
                    (id, asset_id, account_id, source_event_id, acquired_at, original_quantity,
                     remaining_quantity, basis_myr, remaining_basis_myr, basis_status, voided)
                VALUES ('clean-lot', 'usdt', 'wallet', 'clean-acq', '2026-09-21T00:00:00+00:00',
                        '10', '10', 42500000, 42500000, 'KNOWN', 0)
                """
            )
            connection.commit()
            return

        _insert_event(connection, "bad-acq", "SALARY", "2026-09-21T00:00:00+00:00")
        _insert_entry(connection, "bad-acq-debit", "bad-acq", "wallet", "usdt", "DEBIT", "10", 42_500_000)
        _insert_entry(connection, "bad-acq-credit", "bad-acq", "income", "usdt", "CREDIT", "10", 42_500_000)
        _insert_event(connection, "bad-reduction", "EXPENSE", "2026-09-21T00:02:00+00:00")
        _insert_entry(
            connection, "bad-reduction-debit", "bad-reduction", "income", "usdt", "DEBIT", "1", 4_250_000
        )
        _insert_entry(
            connection, "bad-reduction-credit", "bad-reduction", "wallet", "usdt", "CREDIT", "1", 4_250_000
        )
        _insert_event(connection, "bad-rate", "INCOME", "2026-09-21T00:03:00+00:00")
        _insert_entry(
            connection, "bad-rate-debit", "bad-rate", "wallet", "usdt", "DEBIT", "2", 8_500_000, "100"
        )
        _insert_entry(
            connection, "bad-rate-credit", "bad-rate", "income", "usdt", "CREDIT", "2", 8_500_000, "100"
        )

        _insert_card(
            connection,
            id="auth-bad",
            transaction_type="AUTHORIZATION",
            status="AUTHORIZED",
            external_id="auth-bad",
        )
        _insert_card(
            connection,
            id="purchase-bad",
            event_id="bad-acq",
            parent_card_transaction_id="auth-bad",
            external_id="purchase-bad",
            provider="OTHER-PROVIDER",
        )
        _insert_card(
            connection,
            id="refund-one",
            transaction_type="REFUND",
            original_transaction_id="purchase-bad",
            external_id="refund-one",
            merchant_value_myr=60_000_000,
        )
        _insert_card(
            connection,
            id="refund-two",
            transaction_type="REFUND",
            original_transaction_id="purchase-bad",
            external_id="refund-two",
            merchant_value_myr=50_000_000,
        )
        _insert_card(
            connection,
            id="auth-partial",
            transaction_type="AUTHORIZATION",
            status="PARTIALLY_SETTLED",
            external_id="auth-partial",
        )
        _insert_card(
            connection,
            id="purchase-two",
            parent_card_transaction_id="auth-partial",
            external_id="purchase-two",
        )
        _insert_card(
            connection,
            id="purchase-three",
            parent_card_transaction_id="auth-partial",
            external_id="purchase-three",
        )
        connection.commit()


def test_integrity_audit_clean_database_is_read_only(tmp_path: Path) -> None:
    database = tmp_path / "clean.db"
    _prepare_audit_database(database, clean=True)
    before_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    before_mtime = database.stat().st_mtime_ns
    with sqlite3.connect(database) as connection:
        before_rows = connection.execute("SELECT COUNT(*) FROM transaction_events").fetchone()[0]

    report = audit_integrity(database)
    output = tmp_path / "audit.json"
    write_audit_json(report, output)

    assert report["issue_count"] == 0
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == 1
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before_hash
    assert database.stat().st_mtime_ns == before_mtime
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM transaction_events").fetchone()[0] == before_rows


def test_integrity_audit_reports_all_p1_rules(tmp_path: Path) -> None:
    database = tmp_path / "issues.db"
    _prepare_audit_database(database)

    report = audit_integrity(database)
    codes = {issue["code"] for issue in report["issues"]}

    assert codes == {f"AUD-{number:02d}" for number in range(1, 9)}
    assert report["issue_count"] >= 8


def test_integrity_audit_cli_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clean_database = tmp_path / "clean-cli.db"
    _prepare_audit_database(clean_database, clean=True)
    monkeypatch.setattr(sys, "argv", ["maintenance", "audit-integrity", "--database", str(clean_database)])
    assert main() == 0

    issue_database = tmp_path / "issue-cli.db"
    _prepare_audit_database(issue_database)
    output = tmp_path / "issue-cli.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["maintenance", "audit-integrity", "--database", str(issue_database), "--json", str(output)],
    )
    assert main() == 2
    assert json.loads(output.read_text(encoding="utf-8"))["issue_count"] >= 8

    missing = tmp_path / "missing.db"
    monkeypatch.setattr(sys, "argv", ["maintenance", "audit-integrity", "--database", str(missing)])
    assert main() == 1


def test_health() -> None:
    assert TestClient(app).get("/api/health").json() == {"status": "ok"}


def test_decimal_and_micros_are_exact() -> None:
    assert canonical_decimal("0.02000000") == "0.02"
    assert myr_to_micros("4250.1234565") == 4_250_123_456
    assert micros_to_myr(4_250_123_456) == "4250.123456"
    assert parse_decimal(Decimal("0.1")) + parse_decimal("0.2") == Decimal("0.3")
    with pytest.raises(ValueError, match="floating-point"):
        parse_decimal(0.1)  # type: ignore[arg-type]


def test_sqlite_enables_foreign_keys() -> None:
    engine = create_sqlite_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_database_migrates_backs_up_and_restores(tmp_path) -> None:
    database = tmp_path / "source.db"
    assert migrate_database(database) is None
    with sqlite3.connect(database) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample VALUES ('preserved')")
    assert revision == ("0007_recurring_expenses",)

    backup = backup_database(database, tmp_path / "backup.db")
    restored = restore_database(backup, tmp_path / "restored.db")
    with sqlite3.connect(restored) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == ("preserved",)


def test_database_backup_includes_committed_wal_rows(tmp_path) -> None:
    database = tmp_path / "wal-source.db"
    source_connection = sqlite3.connect(database)
    try:
        assert source_connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        source_connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        source_connection.execute("INSERT INTO sample VALUES ('in-wal')")
        source_connection.commit()

        backup = backup_database(database, tmp_path / "wal-backup.db")
    finally:
        source_connection.close()

    with sqlite3.connect(backup) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == ("in-wal",)
