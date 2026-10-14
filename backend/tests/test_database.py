import pytest
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.app.core.database import ping_database, get_db, transaction_scope
from backend.app.models.contact import ContactInquiry


def test_ping_database(db_session: Session):
    """Verify low-overhead ping returns connected status and measured latency."""
    res = ping_database(db_session)
    assert res["status"] == "connected"
    assert isinstance(res["latency_ms"], float)
    assert res["latency_ms"] >= 0.0
    assert res["dialect"] in ("sqlite", "postgresql")


def test_get_db_session_lifecycle():
    """Verify get_db dependency yields a valid session and closes cleanly."""
    gen = get_db()
    session = next(gen)
    assert isinstance(session, Session)
    assert session.is_active

    # Finish generator execution to trigger finally: db.close()
    try:
        next(gen)
    except StopIteration:
        pass


def test_transaction_rollback_on_exception(test_engine):
    """Verify that an exception within a transaction scope aborts and discards changes."""
    session_factory = Session(bind=test_engine)

    with pytest.raises(RuntimeError):
        with transaction_scope(session_factory):
            inquiry = ContactInquiry(
                name="Rollback Test User",
                phone="+91 99999 11111",
                message="This record should not persist.",
            )
            session_factory.add(inquiry)
            raise RuntimeError("Intentional error to test rollback")

    # Verify record was not committed
    queried = session_factory.query(ContactInquiry).filter_by(phone="+91 99999 11111").first()
    assert queried is None
    session_factory.close()
