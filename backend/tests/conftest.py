from collections.abc import Generator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.database import BACKEND_DIR, create_sqlite_engine, get_session
from app.main import app


@pytest.fixture
def client(tmp_path) -> Generator[TestClient]:
    database = tmp_path / "test.db"
    url = f"sqlite:///{database.as_posix()}"
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    engine = create_sqlite_engine(url)
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)

    def session_override() -> Generator[Session]:
        with testing_session() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()
