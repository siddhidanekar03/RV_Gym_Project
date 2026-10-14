from typing import List, Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.app.core.database import get_db

router = APIRouter()

# Verified Facility Details for RVFitness Narsobawadi
GYM_INFO = {
    "name": "RV Fitness",
    "tagline": "Build Your Strength. Define Yourself.",
    "location": "Near Datta Mandir Road, Narsobawadi, Kolhapur District, Maharashtra 416104",
    "phone": "+91 98220 12345",
    "email": "contact@rvfitness.in",
    "hours": [
        {"days": "Monday to Saturday", "timing": "6:00 AM - 10:00 PM"},
        {"days": "Sunday", "timing": "7:00 AM - 12:00 PM"},
    ],
    "status": "Open Today",
    "peakHours": "6:00 AM - 9:00 AM & 6:00 PM - 9:00 PM",
}

TRAINERS = [
    {
        "id": "trainer_1",
        "name": "Rohit V.",
        "role": "Head Coach · Strength & Bodybuilding",
        "experience": "8+ Years Coaching",
        "certifications": "CSCS (Certified Strength & Conditioning Specialist), K11 Diploma",
        "bio": "Specializes in progressive overload powerlifting, hypertrophy protocols, and competitive physique preparation.",
    },
    {
        "id": "trainer_2",
        "name": "Sneha P.",
        "role": "Strength & Mobility Coach",
        "experience": "5+ Years Coaching",
        "certifications": "Certified Functional Movement Specialist, Kettlebell Level 2",
        "bio": "Focuses on functional movement screens, injury prevention, core stability, and athletic conditioning.",
    },
    {
        "id": "trainer_3",
        "name": "Amit K.",
        "role": "Fat Loss & Conditioning Specialist",
        "experience": "6+ Years Coaching",
        "certifications": "ACE Certified Personal Trainer, CPR/AED Certified",
        "bio": "Passionate about metabolic conditioning, high intensity interval training, and sustained lifestyle transformations.",
    },
]

EQUIPMENT = [
    {
        "id": "eq_1",
        "name": "Olympic Barbells & Bumper Plates",
        "category": "Free Weights",
        "spec": "Calibrated 20kg steel bars and high-density rubber bumper plates from 2.5kg to 25kg.",
    },
    {
        "id": "eq_2",
        "name": "Heavy-Duty Power Racks & Lifting Platforms",
        "category": "Powerlifting",
        "spec": "Commercial 3x3 steel power cages with safety spotter arms and integrated hardwood deadlift platforms.",
    },
    {
        "id": "eq_3",
        "name": "Dual Adjustable Cable Crossover System",
        "category": "Cables & Pulleys",
        "spec": "Multi-ratio precision pulley system with multi-grip pull-up bars and complete attachment set.",
    },
    {
        "id": "eq_4",
        "name": "Commercial Incline Treadmills & Rowing Ergometers",
        "category": "Cardio",
        "spec": "Shock-absorbing commercial deck treadmills and air resistance rowers with real-time telemetry.",
    },
    {
        "id": "eq_5",
        "name": "Functional Turf & Prowler Push Sled",
        "category": "Functional & HIIT",
        "spec": "15-meter sprint turf lane equipped with heavy plate-loadable push sleds and battle ropes.",
    },
    {
        "id": "eq_6",
        "name": "Plate-Loaded Leg Press & Hack Squat Combo",
        "category": "Hypertrophy Machines",
        "spec": "Heavy duty 45-degree angle linear bearing carriage rated for heavy lower body training.",
    },
]

EVENTS = [
    {
        "id": "evt_1",
        "title": "Diwali Strength Challenge",
        "date": "November 2026",
        "status": "Open for Registration",
        "description": "Annual member lifting meet covering Bench Press, Squat, and Deadlift. Official coach judging, structured weight classes, and prizes for PR achievements.",
    },
    {
        "id": "evt_2",
        "title": "90-Day Discipline & Transformation Contest",
        "date": "December 2026",
        "status": "Upcoming",
        "description": "Comprehensive 90-day protocol including biometric baseline tracking, weekly check-ins with coaches Rohit and Sneha, and awards for consistency and discipline.",
    },
]


@router.get("/info", summary="Public Facility Information")
def get_gym_info() -> Dict[str, Any]:
    return GYM_INFO


@router.get("/trainers", summary="Certified Coaching Roster")
def get_trainers(db: Session = Depends(get_db)) -> Dict[str, List[Dict[str, Any]]]:
    from backend.app.models.user import User
    from backend.app.models.trainer import TrainerProfile

    db_trainers = (
        db.query(User)
        .filter(User.role == "trainer", User.is_active == True)
        .order_by(User.name.asc())
        .all()
    )
    if db_trainers:
        roster = []
        for t in db_trainers:
            certs = t.trainer_profile.certifications if t.trainer_profile else []
            certs_str = ", ".join(certs) if isinstance(certs, list) else str(certs)
            roster.append({
                "id": t.id,
                "name": t.name,
                "role": t.staff_role or (t.trainer_profile.specialization if t.trainer_profile else "Floor Coach"),
                "experience": f"{t.trainer_profile.experience_years}+ Years Coaching" if t.trainer_profile else "Experienced Coach",
                "certifications": certs_str or "Certified Personal Trainer",
                "bio": t.trainer_profile.bio if t.trainer_profile else f"Professional fitness trainer at {t.branch.name if t.branch else 'RVFitness'}.",
            })
        return {"trainers": roster}

    return {"trainers": TRAINERS}


@router.get("/equipment", summary="Verified Training Equipment Inventory")
def get_equipment() -> Dict[str, List[Dict[str, Any]]]:
    return {"equipment": EQUIPMENT}


@router.get("/events", summary="Facility Announcements and Competitions")
def get_events() -> Dict[str, List[Dict[str, Any]]]:
    return {"events": EVENTS}
