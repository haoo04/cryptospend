import sqlite3
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import create_sqlite_engine
from app.main import app
from app.maintenance import backup_database, migrate_database, restore_database
from app.money import canonical_decimal, micros_to_myr, myr_to_micros, parse_decimal


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
    assert revision == ("0002_trading_cost_basis",)

    backup = backup_database(database, tmp_path / "backup.db")
    restored = restore_database(backup, tmp_path / "restored.db")
    with sqlite3.connect(restored) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == ("preserved",)
