import argparse
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.database import BACKEND_DIR, DEFAULT_DATABASE_PATH


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


def main() -> None:
    parser = argparse.ArgumentParser(description="CryptoSpend database maintenance")
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("destination", type=Path)
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("source", type=Path)
    migrate_parser = subparsers.add_parser("migrate")
    migrate_parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    args = parser.parse_args()

    if args.command == "backup":
        backup_database(DEFAULT_DATABASE_PATH, args.destination)
    elif args.command == "restore":
        restore_database(args.source, DEFAULT_DATABASE_PATH)
    else:
        migrate_database(args.database)


if __name__ == "__main__":
    main()
