import io
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.core.auth import (
    create_user_session,
    SESSION_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
)
from backend.app.core.security import hash_password
from backend.app.models.user import User
from backend.app.models.organization import Organization, Branch
from backend.app.models.announcement import Announcement
from backend.app.models.audit import AuditLog
from backend.app.services.announcement_service import (
    create_announcement,
    publish_announcement,
)
from backend.app.schemas.announcement import AnnouncementCreate


@pytest.fixture
def announcement_fixtures(db_session: Session):
    """Seed multi-branch fixtures and roles for announcement testing."""
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
        b2 = Branch(id="sangli", organization_id=org.id, name="Sangli Regional Campus", code="SGL", is_active=True)
        db_session.add(b2)

    db_session.flush()

    # 3. Users across roles and branches
    # Org Admin
    org_admin = db_session.query(User).filter(User.email == "ann_org_admin@rvfitness.in").first()
    if not org_admin:
        org_admin = User(
            email="ann_org_admin@rvfitness.in",
            hashed_password=hash_password("AdminPass123!"),
            name="Org Executive",
            role="org_admin",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(org_admin)

    # Manager for Narsobawadi
    mgr_nrs = db_session.query(User).filter(User.email == "ann_mgr_nrs@rvfitness.in").first()
    if not mgr_nrs:
        mgr_nrs = User(
            email="ann_mgr_nrs@rvfitness.in",
            hashed_password=hash_password("ManagerPass123!"),
            name="Manager Narsobawadi",
            role="branch_manager",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(mgr_nrs)

    # Manager for Sangli
    mgr_sgl = db_session.query(User).filter(User.email == "ann_mgr_sgl@rvfitness.in").first()
    if not mgr_sgl:
        mgr_sgl = User(
            email="ann_mgr_sgl@rvfitness.in",
            hashed_password=hash_password("ManagerPass123!"),
            name="Manager Sangli",
            role="branch_manager",
            branch_id="sangli",
            is_active=True,
        )
        db_session.add(mgr_sgl)

    # Front Desk Staff for Narsobawadi
    staff_nrs = db_session.query(User).filter(User.email == "ann_staff_nrs@rvfitness.in").first()
    if not staff_nrs:
        staff_nrs = User(
            email="ann_staff_nrs@rvfitness.in",
            hashed_password=hash_password("StaffPass123!"),
            name="Desk Staff Narsobawadi",
            role="front_desk",
            branch_id="narsobawadi",
            is_active=True,
        )
        db_session.add(staff_nrs)

    # Member belonging to Narsobawadi
    member_nrs = db_session.query(User).filter(User.email == "ann_member_nrs@rvfitness.in").first()
    if not member_nrs:
        member_nrs = User(
            email="ann_member_nrs@rvfitness.in",
            hashed_password=hash_password("MemberPass123!"),
            name="Amit Patil",
            role="member",
            branch_id="narsobawadi",
            membership_id="RVF-NRS-ANN",
            membership_status="active",
            valid_until=datetime.now(timezone.utc).date() + timedelta(days=60),
            is_active=True,
        )
        db_session.add(member_nrs)

    # Member belonging to Sangli
    member_sgl = db_session.query(User).filter(User.email == "ann_member_sgl@rvfitness.in").first()
    if not member_sgl:
        member_sgl = User(
            email="ann_member_sgl@rvfitness.in",
            hashed_password=hash_password("MemberPass123!"),
            name="Rajesh Kulkarni",
            role="member",
            branch_id="sangli",
            membership_id="RVF-SGL-ANN",
            membership_status="active",
            valid_until=datetime.now(timezone.utc).date() + timedelta(days=60),
            is_active=True,
        )
        db_session.add(member_sgl)

    db_session.commit()

    return {
        "org": org,
        "branches": {"narsobawadi": b1, "sangli": b2},
        "org_admin": org_admin,
        "mgr_nrs": mgr_nrs,
        "mgr_sgl": mgr_sgl,
        "staff_nrs": staff_nrs,
        "member_nrs": member_nrs,
        "member_sgl": member_sgl,
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


def test_authorized_announcement_creation_and_editing(client: TestClient, db_session: Session, announcement_fixtures):
    """
    1. Authorized announcement creation and editing:
    - Org admin creates org-wide announcement.
    - Branch manager creates announcement for authorized branch.
    - Edit updates fields and records audit log.
    """
    fx = announcement_fixtures
    headers_admin = _auth_headers(client, db_session, fx["org_admin"])

    # 1. Org Admin creates org-wide notice
    res_admin = client.post(
        "/api/announcements",
        headers=headers_admin,
        json={
            "title": "Annual Gym Power Meet 2026",
            "body": "Registration is now open across all RVFitness branches for the state meet.",
            "category": "competition",
            "priority": "high",
            "audience": "public",
            "is_org_wide": True,
            "pinned": True,
        },
    )
    assert res_admin.status_code == 201
    data_admin = res_admin.json()["announcement"]
    assert data_admin["isOrgWide"] is True
    assert data_admin["branchId"] is None
    assert data_admin["title"] == "Annual Gym Power Meet 2026"
    assert data_admin["category"] == "competition"
    admin_ann_id = data_admin["id"]

    # Verify audit log for creation
    audit_create = (
        db_session.query(AuditLog)
        .filter(AuditLog.resource_id == admin_ann_id, AuditLog.action == "announcement.create")
        .first()
    )
    assert audit_create is not None
    assert audit_create.actor_id == fx["org_admin"].id

    # 2. Branch Manager creates notice for authorized branch (narsobawadi)
    headers_mgr = _auth_headers(client, db_session, fx["mgr_nrs"])
    res_mgr = client.post(
        "/api/announcements",
        headers=headers_mgr,
        json={
            "title": "Narsobawadi Sauna Routine Update",
            "body": "The dry sauna will undergo weekly maintenance this Friday between 2 PM and 4 PM.",
            "category": "maintenance",
            "priority": "normal",
            "audience": "members_only",
            "branch_id": "narsobawadi",
            "is_org_wide": False,
        },
    )
    assert res_mgr.status_code == 201
    data_mgr = res_mgr.json()["announcement"]
    assert data_mgr["branchId"] == "narsobawadi"
    assert data_mgr["isOrgWide"] is False
    mgr_ann_id = data_mgr["id"]

    # 3. Branch Manager edits notice
    res_edit = client.put(
        f"/api/announcements/{mgr_ann_id}",
        headers=headers_mgr,
        json={
            "title": "Narsobawadi Sauna Routine Update (Rescheduled)",
            "priority": "urgent",
            "pinned": True,
        },
    )
    assert res_edit.status_code == 200
    updated_mgr = res_edit.json()["announcement"]
    assert updated_mgr["title"] == "Narsobawadi Sauna Routine Update (Rescheduled)"
    assert updated_mgr["priority"] == "urgent"
    assert updated_mgr["pinned"] is True

    # Verify audit log for update
    audit_update = (
        db_session.query(AuditLog)
        .filter(AuditLog.resource_id == mgr_ann_id, AuditLog.action == "announcement.update")
        .first()
    )
    assert audit_update is not None
    assert audit_update.actor_id == fx["mgr_nrs"].id


def test_unauthorized_publishing_and_creation_attempts(client: TestClient, db_session: Session, announcement_fixtures):
    """
    2. Unauthorized publishing and creation attempts:
    - Front desk staff cannot create, publish, or delete notices.
    - Members cannot create, edit, or publish notices.
    - Unauthenticated requests are rejected.
    """
    fx = announcement_fixtures

    # 1. Front Desk attempts to create announcement
    headers_staff = _auth_headers(client, db_session, fx["staff_nrs"])
    res_staff = client.post(
        "/api/announcements",
        headers=headers_staff,
        json={
            "title": "Unauthorized Notice",
            "body": "Desk staff trying to create an announcement.",
            "category": "general",
        },
    )
    assert res_staff.status_code == 403
    assert "Access denied" in res_staff.json()["detail"]

    # 2. Member attempts to create announcement
    headers_member = _auth_headers(client, db_session, fx["member_nrs"])
    res_member = client.post(
        "/api/announcements",
        headers=headers_member,
        json={
            "title": "Member Post",
            "body": "Member trying to publish notice.",
            "category": "general",
        },
    )
    assert res_member.status_code == 403

    # 3. Create a draft notice via Org Admin
    headers_admin = _auth_headers(client, db_session, fx["org_admin"])
    draft_res = client.post(
        "/api/announcements",
        headers=headers_admin,
        json={
            "title": "Confidential Operational Draft",
            "body": "Only management should publish this.",
            "category": "policy",
            "status": "draft",
        },
    )
    assert draft_res.status_code == 201
    draft_id = draft_res.json()["announcement"]["id"]

    # 4. Front Desk attempts to publish the draft
    res_staff_pub = client.post(
        f"/api/announcements/{draft_id}/publish",
        headers=headers_staff,
        json={},
    )
    assert res_staff_pub.status_code == 403

    # 5. Member attempts to publish the draft
    res_member_pub = client.post(
        f"/api/announcements/{draft_id}/publish",
        headers=headers_member,
        json={},
    )
    assert res_member_pub.status_code == 403

    # 6. Unauthenticated request to publish
    client.cookies.clear()
    res_unauth = client.post(f"/api/announcements/{draft_id}/publish", json={})
    assert res_unauth.status_code in (401, 403)


def test_branch_specific_visibility_and_cross_branch_isolation(client: TestClient, db_session: Session, announcement_fixtures):
    """
    3. Branch-specific visibility and cross-branch isolation:
    - Branch manager cannot create or edit announcements in another branch.
    - Branch manager cannot convert announcement to org-wide.
    - Members of Branch A cannot see Branch B's announcements in feed.
    """
    fx = announcement_fixtures

    # Manager Sangli attempts to create notice targeting Narsobawadi
    headers_mgr_sgl = _auth_headers(client, db_session, fx["mgr_sgl"])
    res_cross_create = client.post(
        "/api/announcements",
        headers=headers_mgr_sgl,
        json={
            "title": "Cross Branch Tampering",
            "body": "Manager of Sangli attempting to post to Narsobawadi.",
            "branch_id": "narsobawadi",
        },
    )
    assert res_cross_create.status_code == 403
    assert "assigned branch" in res_cross_create.json()["detail"]

    # Manager Sangli attempts to create org-wide announcement
    res_org_attempt = client.post(
        "/api/announcements",
        headers=headers_mgr_sgl,
        json={
            "title": "Org Wide Claim",
            "body": "Branch manager attempting to declare org-wide broadcast.",
            "is_org_wide": True,
        },
    )
    assert res_org_attempt.status_code == 403
    assert "organization-wide" in res_org_attempt.json()["detail"]

    # Manager Narsobawadi creates a published notice in Narsobawadi
    headers_mgr_nrs = _auth_headers(client, db_session, fx["mgr_nrs"])
    res_nrs = client.post(
        "/api/announcements",
        headers=headers_mgr_nrs,
        json={
            "title": "Narsobawadi Heavy Dumbbells Arrival",
            "body": "New pairs of 55kg and 60kg calibrated dumbbells arrived at Narsobawadi.",
            "branch_id": "narsobawadi",
            "audience": "members_only",
            "status": "published",
        },
    )
    assert res_nrs.status_code == 201
    nrs_ann_id = res_nrs.json()["announcement"]["id"]

    # Manager Sangli creates a published notice in Sangli
    res_sgl = client.post(
        "/api/announcements",
        headers=headers_mgr_sgl,
        json={
            "title": "Sangli Cardio Deck Expansion",
            "body": "New stairmasters installed in Sangli.",
            "branch_id": "sangli",
            "audience": "members_only",
            "status": "published",
        },
    )
    assert res_sgl.status_code == 201
    sgl_ann_id = res_sgl.json()["announcement"]["id"]

    # Manager Sangli attempts to EDIT Narsobawadi's notice (IDOR)
    res_idor_edit = client.put(
        f"/api/announcements/{nrs_ann_id}",
        headers=headers_mgr_sgl,
        json={"title": "Hacked Title"},
    )
    assert res_idor_edit.status_code == 403

    # Manager Sangli attempts to DELETE Narsobawadi's notice (IDOR)
    res_idor_del = client.delete(
        f"/api/announcements/{nrs_ann_id}",
        headers=headers_mgr_sgl,
    )
    assert res_idor_del.status_code == 403

    # Member Narsobawadi queries feed: must see Narsobawadi notice, NOT Sangli notice
    headers_member_nrs = _auth_headers(client, db_session, fx["member_nrs"])
    feed_nrs = client.get("/api/announcements/feed", headers=headers_member_nrs).json()
    feed_nrs_ids = [a["id"] for a in feed_nrs["announcements"]]
    assert nrs_ann_id in feed_nrs_ids
    assert sgl_ann_id not in feed_nrs_ids

    # Member Sangli queries feed: must see Sangli notice, NOT Narsobawadi notice
    headers_member_sgl = _auth_headers(client, db_session, fx["member_sgl"])
    feed_sgl = client.get("/api/announcements/feed", headers=headers_member_sgl).json()
    feed_sgl_ids = [a["id"] for a in feed_sgl["announcements"]]
    assert sgl_ann_id in feed_sgl_ids
    assert nrs_ann_id not in feed_sgl_ids


def test_organization_wide_announcements(client: TestClient, db_session: Session, announcement_fixtures):
    """
    4. Organization-wide announcements:
    - Broadcasts created with is_org_wide=True appear for members of all branches
    - Also appear in the public feed.
    """
    fx = announcement_fixtures
    headers_admin = _auth_headers(client, db_session, fx["org_admin"])

    res = client.post(
        "/api/announcements",
        headers=headers_admin,
        json={
            "title": "All-Branches Independence Day Schedule",
            "body": "All RVFitness facilities will operate under holiday hours: 6:00 AM to 1:00 PM.",
            "category": "facility",
            "audience": "public",
            "is_org_wide": True,
            "status": "published",
        },
    )
    assert res.status_code == 201
    org_ann_id = res.json()["announcement"]["id"]

    # Member at Narsobawadi receives notice
    headers_member_nrs = _auth_headers(client, db_session, fx["member_nrs"])
    feed_nrs = client.get("/api/announcements/feed", headers=headers_member_nrs).json()
    assert any(a["id"] == org_ann_id for a in feed_nrs["announcements"])

    # Member at Sangli receives notice
    headers_member_sgl = _auth_headers(client, db_session, fx["member_sgl"])
    feed_sgl = client.get("/api/announcements/feed", headers=headers_member_sgl).json()
    assert any(a["id"] == org_ann_id for a in feed_sgl["announcements"])

    # Public endpoint returns the notice
    client.cookies.clear()
    pub_res = client.get("/api/announcements/public").json()
    assert any(a["id"] == org_ann_id for a in pub_res["announcements"])


def test_draft_and_unpublished_content_exclusion(client: TestClient, db_session: Session, announcement_fixtures):
    """
    5. Draft and unpublished content exclusion:
    - Drafts are invisible to public and members.
    - Unpublishing a published notice immediately hides it from feeds.
    - Archiving a notice removes it from public and member feeds.
    """
    fx = announcement_fixtures
    headers_admin = _auth_headers(client, db_session, fx["org_admin"])

    # 1. Create a draft notice
    res_draft = client.post(
        "/api/announcements",
        headers=headers_admin,
        json={
            "title": "Draft Internal Concept",
            "body": "This is a draft not yet approved for public eyes.",
            "audience": "public",
            "status": "draft",
        },
    )
    assert res_draft.status_code == 201
    draft_id = res_draft.json()["announcement"]["id"]

    # Public and member feeds must NOT contain draft
    client.cookies.clear()
    pub_res = client.get("/api/announcements/public").json()
    assert not any(a["id"] == draft_id for a in pub_res["announcements"])

    headers_member = _auth_headers(client, db_session, fx["member_nrs"])
    feed_res = client.get("/api/announcements/feed", headers=headers_member).json()
    assert not any(a["id"] == draft_id for a in feed_res["announcements"])

    # 2. Publish the notice
    client.post(f"/api/announcements/{draft_id}/publish", headers=headers_admin, json={})
    pub_res2 = client.get("/api/announcements/public").json()
    assert any(a["id"] == draft_id for a in pub_res2["announcements"])

    # 3. Unpublish the notice back to draft
    client.post(f"/api/announcements/{draft_id}/unpublish", headers=headers_admin)
    pub_res3 = client.get("/api/announcements/public").json()
    assert not any(a["id"] == draft_id for a in pub_res3["announcements"])

    # 4. Archive notice
    client.post(f"/api/announcements/{draft_id}/archive", headers=headers_admin)
    pub_res4 = client.get("/api/announcements/public").json()
    assert not any(a["id"] == draft_id for a in pub_res4["announcements"])


def test_expired_announcement_exclusion(client: TestClient, db_session: Session, announcement_fixtures):
    """
    6. Expired announcement exclusion:
    - Past expiry times exclude notices from public and member feeds.
    - Future scheduled publish times exclude notices until publication time.
    """
    fx = announcement_fixtures
    now = datetime.now(timezone.utc)

    # Past expired notice
    past_ann = Announcement(
        id=str(uuid.uuid4()),
        organization_id=fx["org"].id,
        branch_id="narsobawadi",
        title="Yesterday's Expired Event",
        body="This event has passed and must be excluded from feeds.",
        category="general",
        priority="normal",
        status="published",
        audience="public",
        published_at=now - timedelta(days=2),
        expires_at=now - timedelta(hours=1),
    )
    db_session.add(past_ann)

    # Future scheduled notice
    future_ann = Announcement(
        id=str(uuid.uuid4()),
        organization_id=fx["org"].id,
        branch_id="narsobawadi",
        title="Future Scheduled Notice",
        body="This notice is scheduled for next week and should not display yet.",
        category="general",
        priority="normal",
        status="published",
        audience="public",
        published_at=now + timedelta(days=5),
        expires_at=now + timedelta(days=10),
    )
    db_session.add(future_ann)
    db_session.commit()

    # Public feed verification
    pub_feed = client.get("/api/announcements/public").json()
    pub_ids = [a["id"] for a in pub_feed["announcements"]]
    assert past_ann.id not in pub_ids
    assert future_ann.id not in pub_ids

    # Member feed verification
    headers_member = _auth_headers(client, db_session, fx["member_nrs"])
    mem_feed = client.get("/api/announcements/feed", headers=headers_member).json()
    mem_ids = [a["id"] for a in mem_feed["announcements"]]
    assert past_ann.id not in mem_ids
    assert future_ann.id not in mem_ids


def test_publication_and_expiry_date_validation(client: TestClient, db_session: Session, announcement_fixtures):
    """
    7. Publication and expiry date validation:
    - expires_at <= publish_at is rejected with 422.
    - Invalid enum fields (category, priority, audience) are rejected with 422.
    - Unsafe image URLs are rejected with 422.
    """
    fx = announcement_fixtures
    headers_admin = _auth_headers(client, db_session, fx["org_admin"])
    now = datetime.now(timezone.utc)

    # 1. Invalid date ordering: expires_at before publish_at
    res_bad_dates = client.post(
        "/api/announcements",
        headers=headers_admin,
        json={
            "title": "Invalid Date Ordering",
            "body": "Expires before publication.",
            "publish_at": (now + timedelta(days=5)).isoformat(),
            "expires_at": (now + timedelta(days=2)).isoformat(),
        },
    )
    assert res_bad_dates.status_code == 422

    # 2. Invalid category
    res_bad_cat = client.post(
        "/api/announcements",
        headers=headers_admin,
        json={
            "title": "Invalid Category",
            "body": "Category is not within allowed set.",
            "category": "not_a_real_category",
        },
    )
    assert res_bad_cat.status_code == 422

    # 3. Invalid priority
    res_bad_prio = client.post(
        "/api/announcements",
        headers=headers_admin,
        json={
            "title": "Invalid Priority",
            "body": "Priority is invalid.",
            "priority": "super_urgent_level_99",
        },
    )
    assert res_bad_prio.status_code == 422

    # 4. Invalid audience
    res_bad_aud = client.post(
        "/api/announcements",
        headers=headers_admin,
        json={
            "title": "Invalid Audience",
            "body": "Audience is invalid.",
            "audience": "secret_club_only",
        },
    )
    assert res_bad_aud.status_code == 422

    # 5. Dangerous image protocol (XSS attempt)
    res_bad_img = client.post(
        "/api/announcements",
        headers=headers_admin,
        json={
            "title": "Dangerous Image Protocol",
            "body": "Attacking with javascript pseudo protocol.",
            "image_url": "javascript:alert('xss')",
        },
    )
    assert res_bad_img.status_code == 422


def test_image_upload_security_and_magic_bytes(client: TestClient, db_session: Session, announcement_fixtures):
    """
    8. Media upload security and magic-byte inspection:
    - Valid JPEG file with binary signature succeeds.
    - Disguised text file fails magic-byte check with 400.
    - Files exceeding 5MB are rejected with 413.
    - Unauthorized users (members) are rejected with 403.
    """
    fx = announcement_fixtures
    headers_admin = _auth_headers(client, db_session, fx["org_admin"])

    # 1. Valid JPEG with magic bytes \xff\xd8\xff
    valid_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 200
    res_upload = client.post(
        "/api/announcements/upload-image",
        headers=headers_admin,
        files={"file": ("banner.jpg", io.BytesIO(valid_jpeg), "image/jpeg")},
    )
    assert res_upload.status_code == 200
    img_url = res_upload.json()["imageUrl"]
    assert img_url.startswith("/uploads/announcements/")
    assert img_url.endswith(".jpg")

    # 2. Text disguised as JPEG (Invalid Magic Bytes)
    fake_jpeg = b"This is just a text file claiming to be an image!"
    res_fake = client.post(
        "/api/announcements/upload-image",
        headers=headers_admin,
        files={"file": ("fake.jpg", io.BytesIO(fake_fake := fake_jpeg), "image/jpeg")},
    )
    assert res_fake.status_code == 400
    assert "binary signature" in res_fake.json()["detail"] or "claimed image format" in res_fake.json()["detail"]

    # 3. Oversized file (> 5 MB)
    large_jpeg = b"\xff\xd8\xff" + b"\x00" * (5 * 1024 * 1024 + 100)
    res_large = client.post(
        "/api/announcements/upload-image",
        headers=headers_admin,
        files={"file": ("big.jpg", io.BytesIO(large_jpeg), "image/jpeg")},
    )
    assert res_large.status_code == 413

    # 4. Member attempts upload
    headers_member = _auth_headers(client, db_session, fx["member_nrs"])
    res_mem_upload = client.post(
        "/api/announcements/upload-image",
        headers=headers_member,
        files={"file": ("banner.jpg", io.BytesIO(valid_jpeg), "image/jpeg")},
    )
    assert res_mem_upload.status_code == 403


def test_preview_announcement_authorization(client: TestClient, db_session: Session, announcement_fixtures):
    """
    9. Preview endpoint permissions:
    - Org admin can preview any draft announcement.
    - Branch manager can preview draft for their branch.
    - Branch manager cannot preview draft for other branches.
    - Member cannot access preview mode.
    """
    fx = announcement_fixtures
    headers_admin = _auth_headers(client, db_session, fx["org_admin"])
    headers_mgr_nrs = _auth_headers(client, db_session, fx["mgr_nrs"])
    headers_mgr_sgl = _auth_headers(client, db_session, fx["mgr_sgl"])
    headers_member = _auth_headers(client, db_session, fx["member_nrs"])

    # Narsobawadi Draft
    res_draft_nrs = client.post(
        "/api/announcements",
        headers=headers_mgr_nrs,
        json={
            "title": "Narsobawadi Secret Renovations",
            "body": "Previewing draft layout before unveiling.",
            "branch_id": "narsobawadi",
            "status": "draft",
        },
    )
    assert res_draft_nrs.status_code == 201
    draft_nrs_id = res_draft_nrs.json()["announcement"]["id"]

    # 1. Narsobawadi Manager previews own draft -> 200
    res_prev_own = client.get(f"/api/announcements/{draft_nrs_id}/preview", headers=headers_mgr_nrs)
    assert res_prev_own.status_code == 200
    assert res_prev_own.json()["announcement"]["title"] == "Narsobawadi Secret Renovations"

    # 2. Org Admin previews draft -> 200
    res_prev_admin = client.get(f"/api/announcements/{draft_nrs_id}/preview", headers=headers_admin)
    assert res_prev_admin.status_code == 200

    # 3. Sangli Manager attempts to preview Narsobawadi draft -> 403
    res_prev_cross = client.get(f"/api/announcements/{draft_nrs_id}/preview", headers=headers_mgr_sgl)
    assert res_prev_cross.status_code == 403

    # 4. Member attempts to preview -> 403
    res_prev_mem = client.get(f"/api/announcements/{draft_nrs_id}/preview", headers=headers_member)
    assert res_prev_mem.status_code == 403


def test_public_and_staff_audience_scoping(client: TestClient, db_session: Session, announcement_fixtures):
    """
    10. Public, Member, and Staff Audience Scoping:
    - Public visitors can only access public audience notices.
    - Member feed includes public and members_only notices.
    - Staff feed includes public, members_only, and staff_only operational notices.
    """
    fx = announcement_fixtures
    headers_admin = _auth_headers(client, db_session, fx["org_admin"])
    headers_staff = _auth_headers(client, db_session, fx["staff_nrs"])
    headers_member = _auth_headers(client, db_session, fx["member_nrs"])

    # 1. Create a staff_only operational notice
    res_staff_notice = client.post(
        "/api/announcements",
        headers=headers_admin,
        json={
            "title": "Front Desk Evacuation Drill Checklist",
            "body": "Operational procedures for staff members during the quarterly safety drill.",
            "category": "policy",
            "audience": "staff_only",
            "is_org_wide": True,
            "status": "published",
        },
    )
    assert res_staff_notice.status_code == 201
    staff_ann_id = res_staff_notice.json()["announcement"]["id"]

    # 2. Public feed excludes staff_only notice
    client.cookies.clear()
    pub_feed = client.get("/api/announcements/public").json()
    assert not any(a["id"] == staff_ann_id for a in pub_feed["announcements"])

    # 3. Public GET /{id} on staff_only notice returns 403
    res_direct_pub = client.get(f"/api/announcements/{staff_ann_id}")
    assert res_direct_pub.status_code == 403

    # 4. Member feed excludes staff_only notice
    mem_feed = client.get("/api/announcements/feed", headers=headers_member).json()
    assert not any(a["id"] == staff_ann_id for a in mem_feed["announcements"])

    # 5. Staff feed includes staff_only notice
    staff_feed = client.get("/api/announcements/feed", headers=headers_staff).json()
    assert any(a["id"] == staff_ann_id for a in staff_feed["announcements"])
