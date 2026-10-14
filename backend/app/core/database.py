import time
from typing import Generator, Dict, Any
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from backend.app.core.config import settings
from backend.app.core.logging import logger

# Configure Engine according to dialect
is_sqlite = settings.DATABASE_URL.startswith("sqlite")

engine_kwargs: Dict[str, Any] = {
    "pool_pre_ping": True,
}

if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # Production PostgreSQL pooling parameters
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)

# Session factory with disabled autocommit and autoflush
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy 2.0 declarative models."""
    pass


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency yielding a single database session per request.
    Enforces safe rollback upon unhandled exception and guarantees session closure.
    """
    db: Session = SessionLocal()
    try:
        yield db
    except Exception as exc:
        db.rollback()
        logger.error(f"Database session exception encountered, rolled back transaction: {exc}")
        raise
    finally:
        db.close()


@contextmanager
def transaction_scope(session: Session) -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise


def ping_database(session: Session) -> Dict[str, Any]:
    """
    Execute a low-overhead connectivity check against the active database.
    Returns latency, dialect, and connection status.
    """
    start_time = time.perf_counter()
    session.execute(text("SELECT 1"))
    latency_ms = (time.perf_counter() - start_time) * 1000.0

    return {
        "status": "connected",
        "latency_ms": round(latency_ms, 2),
        "dialect": engine.dialect.name,
    }
