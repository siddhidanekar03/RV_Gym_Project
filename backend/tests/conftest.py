import os
import sys
import tempfile
import pytest
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Ensure backend and workspace are on sys.path
tests_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(tests_dir, ".."))
workspace_dir = os.path.abspath(os.path.join(backend_dir, ".."))
for p in [workspace_dir, backend_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Set test environment variable before importing config
os.environ["ENVIRONMENT"] = "test"

from backend.app.core.database import Base, get_db
from backend.app.main import app
import backend.app.models  # Ensure all models are registered


@pytest.fixture(scope="session")
def test_db_path() -> Generator[str, None, None]:
    """Provide a temporary file path for the test SQLite database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        path = tmp.name
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.fixture(scope="session")
def test_engine(test_db_path: str):
    """Create a persistent test database engine for the test session."""
    engine = create_engine(
        f"sqlite:///{test_db_path}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(test_engine) -> Generator[Session, None, None]:
    """Provide a clean database session per test with automatic post-test cleanup."""
    session_factory = sessionmaker(
        bind=test_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    session = session_factory()
    yield session
    session.close()

    # Clean up all table contents after each test for pristine isolation
    with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def client(test_engine, db_session) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with session per request matching production."""
    def override_get_db():
        session_factory = sessionmaker(
            bind=test_engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        session = session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
