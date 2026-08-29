import os
from collections.abc import Generator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")
DEFAULT_DATABASE_PATH = BACKEND_DIR / "data" / "cryptospend.db"
DATABASE_URL = os.getenv("CRYPTOSPEND_DATABASE_URL", f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}")


class Base(DeclarativeBase):
    pass


def create_sqlite_engine(database_url: str = DATABASE_URL) -> Engine:
    if not database_url.startswith("sqlite"):
        raise ValueError("CryptoSpend currently supports SQLite only")

    is_memory = database_url.endswith(":memory:")
    if database_url.startswith("sqlite:///") and not is_memory:
        Path(database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)

    options: dict[str, object] = {"connect_args": {"check_same_thread": False}}
    if is_memory:
        options["poolclass"] = StaticPool
    engine = create_engine(database_url, **options)

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _record) -> None:  # type: ignore[no-untyped-def]
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


engine = create_sqlite_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Generator[Session]:
    with SessionLocal() as session:
        yield session
