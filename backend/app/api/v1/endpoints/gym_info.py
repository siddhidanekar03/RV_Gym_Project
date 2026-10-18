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


DEFAULT_GALLERY = [
    {
        "id": "gal_1",
        "zone": "Main Free Weights Floor",
        "description": "Heavy dumbbell wall from 2.5kg to 60kg and adjustable commercial incline benches.",
        "image_url": "",
        "status": "In Active Use",
    },
    {
        "id": "gal_2",
        "zone": "Powerlifting Cage Arena",
        "description": "Dual commercial 3x3 steel power cages with calibrated steel plates and deadlift jacks.",
        "image_url": "",
        "status": "In Active Use",
    },
    {
        "id": "gal_3",
        "zone": "Cable & Pulley Suite",
        "description": "Precision dual adjustable pulley station with lat pulldown and low row stations.",
        "image_url": "",
        "status": "In Active Use",
    },
    {
        "id": "gal_4",
        "zone": "Cardio & Conditioning Row",
        "description": "Incline commercial treadmills and air resistance rowers with telemetry displays.",
        "image_url": "",
        "status": "In Active Use",
    },
    {
        "id": "gal_5",
        "zone": "Functional Turf & Sprint Track",
        "description": "15-meter sprint turf lane equipped for prowler sled pushes and kettlebell work.",
        "image_url": "",
        "status": "In Active Use",
    },
    {
        "id": "gal_6",
        "zone": "Locker & Member Recovery",
        "description": "Secured personal lockers, sanitized changing areas, and post-workout recovery zone.",
        "image_url": "",
        "status": "In Active Use",
    },
]


@router.get("/info", summary="Public Facility Information")
def get_gym_info(db: Session = Depends(get_db)) -> Dict[str, Any]:
    from backend.app.models.website_content import WebsiteContent

    res = dict(GYM_INFO)
    hero = db.query(WebsiteContent).filter(WebsiteContent.id == "content_homepage_hero").first()
    if hero and hero.data:
        res["hero"] = hero.data
        if "headline" in hero.data:
            res["tagline"] = hero.data.get("subtitle") or res["tagline"]

    facility = db.query(WebsiteContent).filter(WebsiteContent.id == "content_facility_info").first()
    if facility and facility.data:
        res.update(facility.data)

    hours = db.query(WebsiteContent).filter(WebsiteContent.id == "content_hours").first()
    if hours and hours.data and "hours" in hours.data:
        res["hours"] = hours.data["hours"]

    contact = db.query(WebsiteContent).filter(WebsiteContent.id == "content_contact").first()
    if contact and contact.data:
        if "phone" in contact.data:
            res["phone"] = contact.data["phone"]
        if "email" in contact.data:
            res["email"] = contact.data["email"]
        if "location" in contact.data:
            res["location"] = contact.data["location"]

    banner = db.query(WebsiteContent).filter(WebsiteContent.id == "content_promotions_banner").first()
    if banner and banner.data:
        res["promotionsBanner"] = banner.data

    return res


@router.get("/trainers", summary="Certified Coaching Roster")
def get_trainers(db: Session = Depends(get_db)) -> Dict[str, List[Dict[str, Any]]]:
    from backend.app.models.user import User

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
                "photo_url": t.trainer_profile.photo_url if t.trainer_profile and t.trainer_profile.photo_url else None,
            })
        return {"trainers": roster}

    return {"trainers": TRAINERS}


@router.get("/equipment", summary="Verified Training Equipment Inventory")
def get_equipment(db: Session = Depends(get_db)) -> Dict[str, List[Dict[str, Any]]]:
    from backend.app.models.website_content import EquipmentItem

    db_items = (
        db.query(EquipmentItem)
        .filter(EquipmentItem.is_published == True)
        .order_by(EquipmentItem.display_order.asc(), EquipmentItem.created_at.desc())
        .all()
    )
    if db_items:
        return {
            "equipment": [
                {
                    "id": item.id,
                    "name": item.name,
                    "category": item.category,
                    "spec": item.spec,
                    "brand_model": item.brand_model,
                    "primary_image_url": item.primary_image_url,
                    "images": item.images or [],
                }
                for item in db_items
            ]
        }

    return {"equipment": EQUIPMENT}


@router.get("/gallery", summary="Public Facility Gallery Showcases")
def get_gallery(db: Session = Depends(get_db)) -> Dict[str, List[Dict[str, Any]]]:
    from backend.app.models.website_content import GalleryItem

    db_gallery = (
        db.query(GalleryItem)
        .filter(GalleryItem.is_published == True)
        .order_by(GalleryItem.display_order.asc(), GalleryItem.created_at.desc())
        .all()
    )
    if db_gallery:
        return {
            "gallery": [
                {
                    "id": g.id,
                    "zone": g.zone,
                    "description": g.description,
                    "image_url": g.image_url,
                    "status": g.status,
                }
                for g in db_gallery
            ]
        }

    return {"gallery": DEFAULT_GALLERY}


@router.get("/events", summary="Facility Announcements and Competitions")
def get_events() -> Dict[str, List[Dict[str, Any]]]:
    return {"events": EVENTS}
