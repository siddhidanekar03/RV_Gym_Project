from fastapi import APIRouter
from backend.app.api.v1.endpoints import (
    health,
    gym_info,
    plans,
    auth,
    attendance,
    enrollment,
    contact,
    leaderboard,
    admin,
    billing,
    trainer,
    branches,
)

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(gym_info.router, tags=["Gym Info"])
api_router.include_router(plans.router, tags=["Memberships"])
api_router.include_router(auth.router, tags=["Authentication"])
api_router.include_router(attendance.router, tags=["Attendance"])
api_router.include_router(enrollment.router, tags=["Enrollment"])
api_router.include_router(contact.router, tags=["Contact"])
api_router.include_router(leaderboard.router, tags=["Leaderboard"])
api_router.include_router(admin.router, tags=["Admin"])
api_router.include_router(billing.router, tags=["Billing"])
api_router.include_router(trainer.router, tags=["Trainers"])
api_router.include_router(branches.router, tags=["Branches"])
