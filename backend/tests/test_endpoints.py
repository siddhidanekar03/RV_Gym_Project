import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.models.contact import ContactInquiry
from backend.app.models.membership import Enrollment, MembershipPlan
from backend.app.core.rate_limit import limiter


def test_public_gym_info_endpoints(client: TestClient):
    """Verify public informational endpoints return verified gym data."""
    # 1. Info
    info_res = client.get("/api/info")
    assert info_res.status_code == 200
    assert "RV Fitness" in info_res.json()["name"]
    assert "Narsobawadi" in info_res.json()["location"]

    # 2. Trainers
    trainers_res = client.get("/api/trainers")
    assert trainers_res.status_code == 200
    trainers = trainers_res.json()["trainers"]
    assert len(trainers) >= 3
    assert any(t["name"] == "Rohit V." for t in trainers)

    # 3. Equipment
    eq_res = client.get("/api/equipment")
    assert eq_res.status_code == 200
    equipment = eq_res.json()["equipment"]
    assert len(equipment) >= 6

    # 4. Events
    events_res = client.get("/api/events")
    assert events_res.status_code == 200
    assert len(events_res.json()["events"]) >= 2


def test_plans_endpoint_auto_seeds_and_persists(client: TestClient, db_session: Session):
    """Verify /api/plans queries database and initializes verified plans if unseeded."""
    res = client.get("/api/plans")
    assert res.status_code == 200
    plans = res.json()["plans"]
    assert len(plans) == 3

    monthly = next(p for p in plans if p["id"] == "plan_monthly")
    assert monthly["price"] == 1500
    assert monthly["currency"] == "₹"

    # Verify they exist in the database table
    db_plans = db_session.query(MembershipPlan).all()
    assert len(db_plans) == 3


def test_contact_inquiry_submission(client: TestClient, db_session: Session):
    """Verify contact inquiries are validated and saved to contact_inquiries table."""
    payload = {
        "name": "Sunil Shinde",
        "phone": "+91 98220 77777",
        "email": "sunil@example.com",
        "message": "Looking for personal training guidance on compound lifts.",
    }

    res = client.post("/api/contact", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["success"] is True
    assert "id" in data

    # Verify database persistence
    inquiry = db_session.query(ContactInquiry).filter(ContactInquiry.id == data["id"]).one()
    assert inquiry.name == "Sunil Shinde"
    assert inquiry.phone == "+91 98220 77777"
    assert inquiry.status == "new"


def test_enrollment_submission(client: TestClient, db_session: Session):
    """Verify membership enrollments validate plan and persist to enrollments table."""
    # Ensure plans exist
    client.get("/api/plans")

    payload = {
        "planId": "plan_quarterly",
        "name": "Nikhil Kulkarni",
        "phone": "+91 98220 88888",
        "email": "nikhil@example.com",
        "acceptedTerms": True,
    }

    res = client.post("/api/memberships/enroll", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["success"] is True
    assert data["enrollment"]["planName"] == "Quarterly"
    assert data["enrollment"]["price"] == 4000

    # Verify database persistence
    enrollment = (
        db_session.query(Enrollment)
        .filter(Enrollment.id == data["enrollment"]["id"])
        .one()
    )
    assert enrollment.name == "Nikhil Kulkarni"
    assert enrollment.status == "Pending Verification at Gym Desk"


def test_rate_limiting_enforcement(client: TestClient):
    """Verify rate limiter blocks abusive request volume with HTTP 429."""
    limiter.reset()

    # Trigger contact endpoint rapidly
    payload = {"name": "Bot Tester", "phone": "+91 98220 00000", "message": "Spam"}

    responses = []
    for _ in range(12):
        r = client.post("/api/contact", json=payload)
        responses.append(r.status_code)

    assert 429 in responses
    limiter.reset()
