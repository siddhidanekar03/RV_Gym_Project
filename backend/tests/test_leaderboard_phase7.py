import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from backend.app.core.auth import (
    create_user_session,
    SESSION_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
)
from backend.app.core.security import hash_password
from backend.app.models.user import User
from backend.app.models.organization import Organization, Branch
from backend.app.models.attendance import AttendanceRecord
from backend.app.models.personal_record import PersonalRecord
from backend.app.models.audit import AuditLog
from backend.app.models.leaderboard import PointLedgerEntry
from backend.app.services.leaderboard_service import (
    award_attendance_points,
    award_pr_points,
    reverse_attendance_points,
    record_admin_point_adjustment,
    get_monthly_leaderboard,
    get_member_self_standing,
    update_member_preferences,
    POINTS_ATTENDANCE_VERIFIED,
    POINTS_COACH_VERIFIED_PR,
    POINTS_STREAK_MILESTONE,
)


@pytest.fixture
def leaderboard_fixtures(db_session: Session):
    """Seed multi-branch fixtures and roles for Phase 7 testing."""
    # 1. Organization
    org = db_session.query(Organization).filter(Organization.code == "RVF").first()
    if not org:
        org = Organization(name="RV Fitness Systems", code="RVF", contact_email="contact@rvfitness.in")
        db_session.add(org)
        db_session.flush()

    # 2. Branches
    b1 = db_session.query(Branch).filter(Branch.id == "narsobawadi").first()
    if not b1:
        b1 = Branch(id="narsobawadi", organization_id=org.id, name="Narsobawadi Campus", code="NRS", is_active=True)
        db_session.add(b1)

    b2 = db_session.query(Branch).filter(Branch.id == "sangli").first()
    if not b2:
        b2 = Branch(id="sangli", organization_id=org.id, name="Sangli Campus", code="SGL", is_active=True)
        db_session.add(b2)

    db_session.flush()

    # 3. Users across roles and branches
    org_admin = db_session.query(User).filter(User.email == "lb_admin@rvfitness.in").first()
    if not org_admin:
        org_admin = User(
            email="lb_admin@rvfitness.in",
            hashed_password=hash_password("AdminSecret123!"),
            name="Executive Director",
            role="org_admin",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(org_admin)

    mgr_nrs = db_session.query(User).filter(User.email == "lb_mgr_nrs@rvfitness.in").first()
    if not mgr_nrs:
        mgr_nrs = User(
            email="lb_mgr_nrs@rvfitness.in",
            hashed_password=hash_password("ManagerSecret123!"),
            name="Manager Narsobawadi",
            role="branch_manager",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(mgr_nrs)

    mgr_sgl = db_session.query(User).filter(User.email == "lb_mgr_sgl@rvfitness.in").first()
    if not mgr_sgl:
        mgr_sgl = User(
            email="lb_mgr_sgl@rvfitness.in",
            hashed_password=hash_password("ManagerSecret123!"),
            name="Manager Sangli",
            role="branch_manager",
            branch_id="sangli",
            is_active=True,
        )
        db_session.add(mgr_sgl)

    staff_nrs = db_session.query(User).filter(User.email == "lb_staff_nrs@rvfitness.in").first()
    if not staff_nrs:
        staff_nrs = User(
            email="lb_staff_nrs@rvfitness.in",
            hashed_password=hash_password("StaffSecret123!"),
            name="Desk Staff NRS",
            role="front_desk",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(staff_nrs)

    member_nrs_1 = db_session.query(User).filter(User.email == "lb_mem_nrs1@rvfitness.in").first()
    if not member_nrs_1:
        member_nrs_1 = User(
            email="lb_mem_nrs1@rvfitness.in",
            hashed_password=hash_password("MemberSecret123!"),
            name="Siddhesh Kulkarni",
            role="member",
            branch_id="narsobawadi",
            membership_id="RVF-NRS-001",
            membership_status="active",
            valid_until=date.today() + timedelta(days=90),
            leaderboard_alias="Kingslayer",
            is_leaderboard_visible=True,
            is_active=True,
        )
        db_session.add(member_nrs_1)

    member_nrs_2 = db_session.query(User).filter(User.email == "lb_mem_nrs2@rvfitness.in").first()
    if not member_nrs_2:
        member_nrs_2 = User(
            email="lb_mem_nrs2@rvfitness.in",
            hashed_password=hash_password("MemberSecret123!"),
            name="Aniket Deshmukh",
            role="member",
            branch_id="narsobawadi",
            membership_id="RVF-NRS-002",
            membership_status="active",
            valid_until=date.today() + timedelta(days=90),
            leaderboard_alias="IronTitan",
            is_leaderboard_visible=True,
            is_active=True,
        )
        db_session.add(member_nrs_2)

    member_sgl_1 = db_session.query(User).filter(User.email == "lb_mem_sgl1@rvfitness.in").first()
    if not member_sgl_1:
        member_sgl_1 = User(
            email="lb_mem_sgl1@rvfitness.in",
            hashed_password=hash_password("MemberSecret123!"),
            name="Pooja Shinde",
            role="member",
            branch_id="sangli",
            membership_id="RVF-SGL-001",
            membership_status="active",
            valid_until=date.today() + timedelta(days=90),
            leaderboard_alias="Valkyrie",
            is_leaderboard_visible=True,
            is_active=True,
        )
        db_session.add(member_sgl_1)

    db_session.commit()

    return {
        "org": org,
        "branches": {"narsobawadi": b1, "sangli": b2},
        "org_admin": org_admin,
        "mgr_nrs": mgr_nrs,
        "mgr_sgl": mgr_sgl,
        "staff_nrs": staff_nrs,
        "member_nrs_1": member_nrs_1,
        "member_nrs_2": member_nrs_2,
        "member_sgl_1": member_sgl_1,
    }


def _auth_headers(client: TestClient, db: Session, user: User) -> Dict[str, str]:
    """Helper to establish a verified cookie session and CSRF headers."""
    session, token, csrf = create_user_session(db, user)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    client.cookies.set(CSRF_COOKIE_NAME, csrf)
    return {
        CSRF_HEADER_NAME: csrf,
        "x-csrf-token": csrf,
        "Cookie": f"{SESSION_COOKIE_NAME}={token}; {CSRF_COOKIE_NAME}={csrf}",
    }


def test_01_eligible_attendance_generates_correct_points(db_session: Session, leaderboard_fixtures):
    """1. Eligible attendance creates exactly one point ledger entry with 10 points."""
    fx = leaderboard_fixtures
    mem = fx["member_nrs_1"]

    att = AttendanceRecord(
        user_id=mem.id,
        branch_id="narsobawadi",
        check_in_date=date(2026, 10, 15),
        source="qr",
        method="qr",
    )
    db_session.add(att)
    db_session.flush()

    entry = award_attendance_points(db_session, att)
    db_session.commit()

    assert entry is not None
    assert entry.points == POINTS_ATTENDANCE_VERIFIED
    assert entry.user_id == mem.id
    assert entry.source_type == "attendance_verified"
    assert entry.source_id == att.id
    assert entry.year == 2026
    assert entry.month == 10


def test_02_duplicate_attendance_cannot_generate_duplicate_points(db_session: Session, leaderboard_fixtures):
    """2. Repeated calls or duplicate check-in events on the same date cannot award points twice."""
    fx = leaderboard_fixtures
    mem = fx["member_nrs_1"]

    att1 = AttendanceRecord(
        user_id=mem.id,
        branch_id="narsobawadi",
        check_in_date=date(2026, 10, 16),
        source="qr",
        method="qr",
    )
    db_session.add(att1)
    db_session.flush()

    first_entry = award_attendance_points(db_session, att1)
    db_session.commit()

    # Second call with the exact same record returns the existing entry
    second_entry = award_attendance_points(db_session, att1)
    assert second_entry.id == first_entry.id

    # Simulated second record on same date for same user at different branch
    att2 = AttendanceRecord(
        user_id=mem.id,
        branch_id="sangli",
        check_in_date=date(2026, 10, 16),
        source="manual",
        method="desk_manual",
    )
    db_session.add(att2)
    db_session.flush()

    # Daily cap safeguard prevents awarding points again on same calendar date
    third_entry = award_attendance_points(db_session, att2)
    assert third_entry.id == first_entry.id

    # Verify database has strictly 1 entry for this date
    count = (
        db_session.query(PointLedgerEntry)
        .filter(
            PointLedgerEntry.user_id == mem.id,
            PointLedgerEntry.event_date == date(2026, 10, 16),
        )
        .count()
    )
    assert count == 1


def test_03_failed_or_rejected_checkin_earns_no_points(db_session: Session, leaderboard_fixtures):
    """3. Failed check-ins without an attendance record or records without user_id earn 0 points."""
    unregistered_att = AttendanceRecord(
        user_id=None,
        branch_id="narsobawadi",
        check_in_date=date(2026, 10, 17),
        member_name="Walk-In Guest",
        member_phone="9876543210",
        source="manual",
        method="desk_manual",
    )
    db_session.add(unregistered_att)
    db_session.flush()

    entry = award_attendance_points(db_session, unregistered_att)
    assert entry is None

    # Count of ledger entries remains 0
    count = db_session.query(PointLedgerEntry).filter(PointLedgerEntry.source_id == unregistered_att.id).count()
    assert count == 0


def test_04_member_opt_in_out_and_alias_update_self_only(client: TestClient, db_session: Session, leaderboard_fixtures):
    """4. Members can opt in, opt out, and update only their own gaming alias."""
    fx = leaderboard_fixtures
    mem = fx["member_nrs_1"]
    headers = _auth_headers(client, db_session, mem)

    # Valid update
    res = client.put(
        "/api/leaderboard/preferences",
        json={"alias": "Shadow_Hunter", "isLeaderboardVisible": False},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["alias"] == "Shadow_Hunter"
    assert data["isLeaderboardVisible"] is False

    # Verify in DB
    db_session.refresh(mem)
    assert mem.leaderboard_alias == "Shadow_Hunter"
    assert mem.is_leaderboard_visible is False

    # Attempting to claim an already taken alias returns 409
    mem2 = fx["member_nrs_2"]
    headers2 = _auth_headers(client, db_session, mem2)
    res_conflict = client.put(
        "/api/leaderboard/preferences",
        json={"alias": "shadow_hunter"},  # Case-insensitive collision
        headers=headers2,
    )
    assert res_conflict.status_code == 409
    assert "already claimed" in res_conflict.json()["detail"].lower()

    # Invalid alias characters (< 3 chars or spaces) returns 422
    res_invalid = client.put(
        "/api/leaderboard/preferences",
        json={"alias": "ab"},
        headers=headers2,
    )
    assert res_invalid.status_code == 422


def test_05_opted_out_members_excluded_from_public_rankings(client: TestClient, db_session: Session, leaderboard_fixtures):
    """5. Opted-out members never appear in public rankings."""
    fx = leaderboard_fixtures
    mem_visible = fx["member_nrs_2"]
    mem_hidden = fx["member_nrs_1"]

    # Ensure visibility flags
    mem_visible.is_leaderboard_visible = True
    mem_hidden.is_leaderboard_visible = False
    db_session.commit()

    # Add points for both members in October 2026
    e1 = PointLedgerEntry(
        id=str(uuid.uuid4()),
        user_id=mem_visible.id,
        organization_id=fx["org"].id,
        branch_id="narsobawadi",
        source_type="attendance_verified",
        source_id=str(uuid.uuid4()),
        points=30,
        event_date=date(2026, 10, 1),
        year=2026,
        month=10,
    )
    e2 = PointLedgerEntry(
        id=str(uuid.uuid4()),
        user_id=mem_hidden.id,
        organization_id=fx["org"].id,
        branch_id="narsobawadi",
        source_type="attendance_verified",
        source_id=str(uuid.uuid4()),
        points=50,
        event_date=date(2026, 10, 1),
        year=2026,
        month=10,
    )
    db_session.add_all([e1, e2])
    db_session.commit()

    res = client.get("/api/leaderboard?year=2026&month=10&branch_id=narsobawadi")
    assert res.status_code == 200
    data = res.json()
    aliases = [item["name"] for item in data["leaderboard"]]

    # Visible member is present
    assert mem_visible.leaderboard_alias in aliases
    # Hidden member is strictly absent
    assert mem_hidden.leaderboard_alias not in aliases
    assert mem_hidden.name not in aliases


def test_06_public_responses_do_not_expose_personal_information(client: TestClient, db_session: Session, leaderboard_fixtures):
    """6. Public responses never expose real names, emails, phone numbers, or member IDs."""
    fx = leaderboard_fixtures
    mem = fx["member_nrs_2"]

    res = client.get("/api/leaderboard?year=2026&month=10&branch_id=narsobawadi")
    assert res.status_code == 200
    data = res.json()

    for item in data["leaderboard"]:
        # Verify no PII fields exist in public schema
        assert "email" not in item
        assert "phone" not in item
        assert "member_id" not in item
        assert "membershipId" not in item
        assert "userId" not in item

        # Verify legal name is not exposed
        assert item["name"] != mem.name
        assert item["alias"] != mem.name


def test_07_branch_rankings_enforce_branch_isolation(client: TestClient, db_session: Session, leaderboard_fixtures):
    """7. Branch rankings strictly isolate standings by branch."""
    fx = leaderboard_fixtures
    mem_nrs = fx["member_nrs_2"]
    mem_sgl = fx["member_sgl_1"]

    e_sgl = PointLedgerEntry(
        id=str(uuid.uuid4()),
        user_id=mem_sgl.id,
        organization_id=fx["org"].id,
        branch_id="sangli",
        source_type="attendance_verified",
        source_id=str(uuid.uuid4()),
        points=40,
        event_date=date(2026, 10, 2),
        year=2026,
        month=10,
    )
    db_session.add(e_sgl)
    db_session.commit()

    # Query Narsobawadi
    res_nrs = client.get("/api/leaderboard?year=2026&month=10&branch_id=narsobawadi")
    assert res_nrs.status_code == 200
    names_nrs = [item["name"] for item in res_nrs.json()["leaderboard"]]
    assert mem_sgl.leaderboard_alias not in names_nrs

    # Query Sangli
    res_sgl = client.get("/api/leaderboard?year=2026&month=10&branch_id=sangli")
    assert res_sgl.status_code == 200
    names_sgl = [item["name"] for item in res_sgl.json()["leaderboard"]]
    assert mem_sgl.leaderboard_alias in names_sgl
    assert mem_nrs.leaderboard_alias not in names_sgl


def test_08_organization_rankings_follow_eligibility_rules(client: TestClient, db_session: Session, leaderboard_fixtures):
    """8. Organization rankings include eligible participating members across all branches."""
    fx = leaderboard_fixtures
    mem_nrs = fx["member_nrs_2"]
    mem_sgl = fx["member_sgl_1"]

    db_session.add_all([
        PointLedgerEntry(
            id=str(uuid.uuid4()),
            user_id=mem_nrs.id,
            organization_id=fx["org"].id,
            branch_id="narsobawadi",
            source_type="attendance_verified",
            source_id=str(uuid.uuid4()),
            points=50,
            event_date=date(2026, 10, 5),
            year=2026,
            month=10,
        ),
        PointLedgerEntry(
            id=str(uuid.uuid4()),
            user_id=mem_sgl.id,
            organization_id=fx["org"].id,
            branch_id="sangli",
            source_type="attendance_verified",
            source_id=str(uuid.uuid4()),
            points=40,
            event_date=date(2026, 10, 5),
            year=2026,
            month=10,
        ),
    ])
    db_session.commit()

    res_org = client.get("/api/leaderboard?year=2026&month=10&branch_id=all")
    assert res_org.status_code == 200
    data = res_org.json()
    assert data["scope"] == "organization"
    names = [item["name"] for item in data["leaderboard"]]

    assert mem_nrs.leaderboard_alias in names
    assert mem_sgl.leaderboard_alias in names


def test_09_month_year_boundaries_and_deterministic_tie_breaking(db_session: Session, leaderboard_fixtures):
    """9. Month boundaries isolate data and tie-breaking orders by points, then distinct days, then timestamp."""
    fx = leaderboard_fixtures
    u1 = fx["member_nrs_1"]
    u2 = fx["member_nrs_2"]

    u1.is_leaderboard_visible = True
    u2.is_leaderboard_visible = True
    db_session.commit()

    # Add 20 points in September 2026 for u1
    past_entry = PointLedgerEntry(
        id=str(uuid.uuid4()),
        user_id=u1.id,
        organization_id=fx["org"].id,
        branch_id="narsobawadi",
        source_type="attendance_verified",
        source_id=str(uuid.uuid4()),
        points=20,
        event_date=date(2026, 9, 20),
        year=2026,
        month=9,
    )
    db_session.add(past_entry)

    # In November 2026: Both u1 and u2 have 20 points
    # u1 achieves 20 points across 2 distinct days (10 + 10)
    # u2 achieves 20 points across 1 day (e.g. attendance + streak milestone)
    t1 = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)

    db_session.add_all([
        PointLedgerEntry(
            id=str(uuid.uuid4()),
            user_id=u1.id,
            organization_id=fx["org"].id,
            branch_id="narsobawadi",
            source_type="attendance_verified",
            source_id=str(uuid.uuid4()),
            points=10,
            event_date=date(2026, 11, 1),
            year=2026,
            month=11,
            created_at=t1,
        ),
        PointLedgerEntry(
            id=str(uuid.uuid4()),
            user_id=u1.id,
            organization_id=fx["org"].id,
            branch_id="narsobawadi",
            source_type="attendance_verified",
            source_id=str(uuid.uuid4()),
            points=10,
            event_date=date(2026, 11, 2),
            year=2026,
            month=11,
            created_at=t2,
        ),
        PointLedgerEntry(
            id=str(uuid.uuid4()),
            user_id=u2.id,
            organization_id=fx["org"].id,
            branch_id="narsobawadi",
            source_type="attendance_verified",
            source_id=str(uuid.uuid4()),
            points=20,
            event_date=date(2026, 11, 1),
            year=2026,
            month=11,
            created_at=t1,
        ),
    ])
    db_session.commit()

    # Query September 2026
    entries_sep, count_sep = get_monthly_leaderboard(db_session, year=2026, month=9)
    assert count_sep == 1
    assert entries_sep[0].points == 20

    # Query November 2026
    entries_nov, count_nov = get_monthly_leaderboard(db_session, year=2026, month=11)
    assert count_nov == 2
    # Both have 20 points, but u1 has 2 distinct days vs u2 with 1 distinct day
    assert entries_nov[0].points == 20
    assert entries_nov[1].points == 20
    assert entries_nov[0].distinctDays == 2
    assert entries_nov[1].distinctDays == 1
    assert entries_nov[0].alias == u1.leaderboard_alias
    assert entries_nov[1].alias == u2.leaderboard_alias


def test_10_concurrent_processing_does_not_double_award_points(db_session: Session, leaderboard_fixtures):
    """10. Database unique constraint uq_point_ledger_source prevents duplicate ledger creation."""
    fx = leaderboard_fixtures
    mem = fx["member_nrs_1"]
    src_id = str(uuid.uuid4())

    entry1 = PointLedgerEntry(
        id=str(uuid.uuid4()),
        user_id=mem.id,
        organization_id=fx["org"].id,
        branch_id="narsobawadi",
        source_type="attendance_verified",
        source_id=src_id,
        points=10,
        event_date=date(2026, 10, 18),
        year=2026,
        month=10,
    )
    db_session.add(entry1)
    db_session.commit()

    entry2 = PointLedgerEntry(
        id=str(uuid.uuid4()),
        user_id=mem.id,
        organization_id=fx["org"].id,
        branch_id="narsobawadi",
        source_type="attendance_verified",
        source_id=src_id,  # Identical source_type and source_id
        points=10,
        event_date=date(2026, 10, 18),
        year=2026,
        month=10,
    )
    db_session.add(entry2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_11_attendance_reversals_and_reconciliations_scoring_policy(db_session: Session, leaderboard_fixtures):
    """11. Attendance reversal inserts negative compensating entry and preserves audit history."""
    fx = leaderboard_fixtures
    mem = fx["member_nrs_1"]
    admin = fx["org_admin"]

    att = AttendanceRecord(
        user_id=mem.id,
        branch_id="narsobawadi",
        check_in_date=date(2026, 10, 19),
        source="qr",
        method="qr",
    )
    db_session.add(att)
    db_session.flush()

    award_attendance_points(db_session, att)
    db_session.commit()

    # Reversal
    rev_entry = reverse_attendance_points(
        db=db_session,
        attendance_record_id=att.id,
        actor_id=admin.id,
        reason="Mistaken duplicate scan flagged by supervisor",
    )
    db_session.commit()

    assert rev_entry is not None
    assert rev_entry.points == -10
    assert rev_entry.source_type == "attendance_reversal"

    # Verify audit log created
    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == "leaderboard.points_reversed",
            AuditLog.resource_id == att.id,
        )
        .first()
    )
    assert audit is not None
    assert audit.actor_id == admin.id


def test_12_unauthorized_administrative_adjustments_rejected(client: TestClient, db_session: Session, leaderboard_fixtures):
    """12. Unauthorized users and cross-branch managers cannot adjust points."""
    fx = leaderboard_fixtures
    mem = fx["member_nrs_1"]
    staff = fx["staff_nrs"]
    mgr_sgl = fx["mgr_sgl"]

    # 1. Regular member attempting adjustment returns 403
    h_mem = _auth_headers(client, db_session, mem)
    res_mem = client.post(
        "/api/leaderboard/adjust",
        json={"userId": mem.id, "points": 15, "reason": "Self bonus attempt"},
        headers=h_mem,
    )
    assert res_mem.status_code == 403

    # 2. Front desk staff attempting adjustment returns 403
    h_staff = _auth_headers(client, db_session, staff)
    res_staff = client.post(
        "/api/leaderboard/adjust",
        json={"userId": mem.id, "points": 15, "reason": "Staff desk adjustment"},
        headers=h_staff,
    )
    assert res_staff.status_code == 403

    # 3. Sangli branch manager attempting adjustment for Narsobawadi member returns 403
    h_mgr_sgl = _auth_headers(client, db_session, mgr_sgl)
    res_cross = client.post(
        "/api/leaderboard/adjust",
        json={"userId": mem.id, "points": 15, "reason": "Cross branch attempt"},
        headers=h_mgr_sgl,
    )
    assert res_cross.status_code == 403


def test_13_authorized_adjustments_require_reason_and_generate_audit_log(client: TestClient, db_session: Session, leaderboard_fixtures):
    """13. Authorized administrative adjustment requires a non-empty reason and creates an audit record."""
    fx = leaderboard_fixtures
    admin = fx["org_admin"]
    mem = fx["member_nrs_1"]
    headers = _auth_headers(client, db_session, admin)

    # Missing reason returns 422
    res_empty = client.post(
        "/api/leaderboard/adjust",
        json={"userId": mem.id, "points": 25, "reason": "   "},
        headers=headers,
    )
    assert res_empty.status_code == 422

    # Valid adjustment
    res_valid = client.post(
        "/api/leaderboard/adjust",
        json={
            "userId": mem.id,
            "points": 25,
            "reason": "Quarterly gym floor tournament sportsmanship prize",
        },
        headers=headers,
    )
    assert res_valid.status_code == 200
    data = res_valid.json()
    assert data["success"] is True
    assert data["pointsAdjusted"] == 25

    # Verify audit log
    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == "leaderboard.admin_adjustment",
            AuditLog.resource_id == mem.id,
        )
        .first()
    )
    assert audit is not None
    assert audit.actor_id == admin.id
    assert audit.details["points"] == 25


def test_14_member_self_standing_shows_own_rank_when_opted_out(client: TestClient, db_session: Session, leaderboard_fixtures):
    """14. Member's own rank and progress remain visible to them via /api/leaderboard/me even when opted out."""
    fx = leaderboard_fixtures
    mem = fx["member_nrs_1"]
    mem.is_leaderboard_visible = False
    db_session.commit()

    headers = _auth_headers(client, db_session, mem)
    res = client.get("/api/leaderboard/me?year=2026&month=10", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["isLeaderboardVisible"] is False
    assert data["alias"] is not None
    assert "points" in data
    assert "distinctDays" in data
    assert "tier" in data


def test_15_scoring_rules_endpoint_accessible(client: TestClient):
    """15. Transparent scoring rules and anti-abuse policies are accessible to all members."""
    res = client.get("/api/leaderboard/rules")
    assert res.status_code == 200
    data = res.json()

    assert "rules" in data
    assert isinstance(data["rules"], list)
    assert len(data["rules"]) >= 3
    assert "antiAbusePolicy" in data
    assert "anti-abuse" in data["antiAbusePolicy"].lower()
