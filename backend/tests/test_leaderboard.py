from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.core.security import hash_password
from backend.app.models.user import User
from backend.app.models.personal_record import PersonalRecord


def test_leaderboard_truthful_empty_state(client: TestClient):
    """Verify leaderboard returns empty list when no verified PR records exist (no fabricated data)."""
    res = client.get("/api/leaderboard")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data["leaderboard"], list)
    assert len(data["leaderboard"]) == 0
    assert "updatedAt" in data


def test_leaderboard_dynamic_calculation_and_pii_masking(client: TestClient, db_session: Session):
    """Verify dynamic leaderboard calculates Power Total and masks member surnames."""
    # Member 1: Higher total
    u1 = User(
        email="athlete1@rvfitness.in",
        hashed_password=hash_password("pw123456"),
        name="Prathamesh Patil",
        role="member",
        streak_days=15,
    )
    # Member 2: Lower total
    u2 = User(
        email="athlete2@rvfitness.in",
        hashed_password=hash_password("pw123456"),
        name="Vaibhav Mane",
        role="member",
        streak_days=20,
    )
    db_session.add_all([u1, u2])
    db_session.commit()

    # Add verified PRs for u1 (Total = 115 + 160 + 205 = 480 kg)
    db_session.add_all([
        PersonalRecord(user_id=u1.id, exercise_name="bench_press", value=Decimal("115.0"), is_coach_verified=True),
        PersonalRecord(user_id=u1.id, exercise_name="squat", value=Decimal("160.0"), is_coach_verified=True),
        PersonalRecord(user_id=u1.id, exercise_name="deadlift", value=Decimal("205.0"), is_coach_verified=True),
    ])

    # Add verified PRs for u2 (Total = 100 + 140 + 190 = 430 kg)
    db_session.add_all([
        PersonalRecord(user_id=u2.id, exercise_name="bench_press", value=Decimal("100.0"), is_coach_verified=True),
        PersonalRecord(user_id=u2.id, exercise_name="squat", value=Decimal("140.0"), is_coach_verified=True),
        PersonalRecord(user_id=u2.id, exercise_name="deadlift", value=Decimal("190.0"), is_coach_verified=True),
    ])
    db_session.commit()

    res = client.get("/api/leaderboard")
    assert res.status_code == 200
    entries = res.json()["leaderboard"]

    assert len(entries) == 2
    # Rank 1: Prathamesh P. with 480 kg
    assert entries[0]["rank"] == 1
    assert entries[0]["name"] == "Prathamesh P."  # Surname masked
    assert entries[0]["score"] == "480 kg"
    assert entries[0]["streak"] == 15

    # Rank 2: Vaibhav M. with 430 kg
    assert entries[1]["rank"] == 2
    assert entries[1]["name"] == "Vaibhav M."
    assert entries[1]["score"] == "430 kg"
