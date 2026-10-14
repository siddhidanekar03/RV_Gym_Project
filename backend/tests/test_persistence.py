from datetime import date, datetime, timezone
from decimal import Decimal
import pytest
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError

from backend.app.models.membership import MembershipPlan, Enrollment
from backend.app.models.user import User
from backend.app.models.attendance import AttendanceRecord
from backend.app.models.personal_record import PersonalRecord
from backend.app.models.contact import ContactInquiry
from backend.app.models.audit import AuditLog


def test_entities_persist_across_independent_sessions(test_engine):
    """
    Verify complete entity lifecycle and relational integrity persist
    across entirely independent database sessions (simulating server restarts).
    """
    SessionFactory = sessionmaker(bind=test_engine, expire_on_commit=False)

    # === SESSION 1: Create and Commit Records ===
    session1: Session = SessionFactory()

    plan = MembershipPlan(
        id="plan_quarterly_persist",
        name="Quarterly Strength",
        price=Decimal("4000.00"),
        currency="₹",
        billing_cycle="per 3 months",
        duration_days=90,
        is_featured=True,
        is_active=True,
        perks=["Full gym floor access", "Priority locker allocation"],
    )
    session1.add(plan)
    session1.flush()

    user = User(
        email="persist_member@rvfitness.in",
        hashed_password="secure_argon2_hashed_value",
        name="Prathamesh Patil",
        phone="+91 98220 11111",
        role="member",
        membership_id="RVF-2026-999",
        membership_plan_id=plan.id,
        membership_status="active",
        member_since=date(2026, 7, 1),
        valid_until=date(2026, 12, 31),
        streak_days=28,
        is_active=True,
    )
    session1.add(user)
    session1.flush()

    enrollment = Enrollment(
        plan_id=plan.id,
        name=user.name,
        phone=user.phone,
        email=user.email,
        price=plan.price,
        currency=plan.currency,
        status="pending_verification",
        accepted_terms=True,
        notes="Enrolled online for Q4 strength block",
    )
    session1.add(enrollment)

    today = date(2026, 10, 14)
    attendance = AttendanceRecord(
        user_id=user.id,
        check_in_date=today,
        method="portal",
        notes="Evening strength session",
    )
    session1.add(attendance)

    pr = PersonalRecord(
        user_id=user.id,
        exercise_name="bench_press",
        value=Decimal("115.00"),
        unit="kg",
        reps=1,
        is_coach_verified=True,
    )
    session1.add(pr)

    inquiry = ContactInquiry(
        name="Prospective Athlete",
        phone="+91 98220 22222",
        email="athlete@example.com",
        message="Interested in competitive powerlifting coaching.",
        status="new",
    )
    session1.add(inquiry)

    audit = AuditLog(
        actor_id=user.id,
        action="user.enrollment_created",
        resource_type="enrollment",
        resource_id=enrollment.id,
        details={"plan_name": plan.name, "amount": str(plan.price)},
        ip_address="127.0.0.1",
    )
    session1.add(audit)

    session1.commit()
    session1.close()  # Terminate session 1 completely

    # === SESSION 2: Verify Persistence in Fresh Session ===
    session2: Session = SessionFactory()

    queried_plan = session2.query(MembershipPlan).filter_by(id="plan_quarterly_persist").one()
    assert queried_plan.name == "Quarterly Strength"
    assert queried_plan.price == Decimal("4000.00")
    assert "Priority locker allocation" in queried_plan.perks

    queried_user = session2.query(User).filter_by(email="persist_member@rvfitness.in").one()
    assert queried_user.name == "Prathamesh Patil"
    assert queried_user.membership_plan_id == queried_plan.id
    assert queried_user.membership_status == "active"
    assert queried_user.streak_days == 28

    queried_attendance = session2.query(AttendanceRecord).filter_by(user_id=queried_user.id).one()
    assert queried_attendance.check_in_date == today
    assert queried_attendance.method == "portal"

    queried_pr = session2.query(PersonalRecord).filter_by(user_id=queried_user.id, exercise_name="bench_press").one()
    assert queried_pr.value == Decimal("115.00")
    assert queried_pr.is_coach_verified is True

    queried_inquiry = session2.query(ContactInquiry).filter_by(phone="+91 98220 22222").one()
    assert queried_inquiry.name == "Prospective Athlete"
    assert queried_inquiry.status == "new"

    queried_audit = session2.query(AuditLog).filter_by(actor_id=queried_user.id).one()
    assert queried_audit.action == "user.enrollment_created"
    assert queried_audit.details["plan_name"] == "Quarterly Strength"

    session2.close()


def test_duplicate_daily_checkin_prevention(test_engine):
    """
    Verify database engine rejects duplicate check-ins for the same user
    on the same calendar date via the compound unique constraint.
    """
    SessionFactory = sessionmaker(bind=test_engine)
    session: Session = SessionFactory()

    user = User(
        email="checkin_test@rvfitness.in",
        hashed_password="pw_hash_test_value",
        name="Daily Check-in Test Member",
    )
    session.add(user)
    session.commit()

    today = date(2026, 10, 14)

    # First check-in succeeds
    checkin_1 = AttendanceRecord(
        user_id=user.id,
        check_in_date=today,
        method="portal",
    )
    session.add(checkin_1)
    session.commit()

    # Second check-in on the exact same date must fail with IntegrityError
    checkin_2 = AttendanceRecord(
        user_id=user.id,
        check_in_date=today,
        method="rfid",
    )
    session.add(checkin_2)

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()

    # Verify only 1 record exists in the database
    count = session.query(AttendanceRecord).filter_by(user_id=user.id, check_in_date=today).count()
    assert count == 1

    session.close()
