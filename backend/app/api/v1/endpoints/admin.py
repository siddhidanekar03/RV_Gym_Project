from datetime import date, datetime
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.app.core.database import get_db
from backend.app.core.auth import require_roles
from backend.app.models.user import User
from backend.app.models.membership import Enrollment
from backend.app.models.attendance import AttendanceRecord
from backend.app.models.contact import ContactInquiry
from backend.app.models.audit import AuditLog
from backend.app.schemas.admin import AdminOverviewResponse, AdminContactItem, StaffDutyItem
from backend.app.schemas.membership import EnrollmentDetail

router = APIRouter()


@router.get(
    "/admin/overview",
    response_model=AdminOverviewResponse,
    dependencies=[Depends(require_roles("admin", "manager", "staff"))],
    summary="Staff Operations Desk Overview",
)
def get_admin_overview(
    user: User = Depends(require_roles("admin", "manager", "staff")),
    db: Session = Depends(get_db),
) -> AdminOverviewResponse:
    today = date.today()

    # 1. Truthful member count (active members in the database)
    total_members = (
        db.query(func.count(User.id))
        .filter(User.role == "member", User.is_active == True)
        .scalar()
        or 0
    )

    # 2. Truthful active today count (actual check-in records recorded today)
    active_today = (
        db.query(func.count(func.distinct(AttendanceRecord.user_id)))
        .filter(AttendanceRecord.check_in_date == today)
        .scalar()
        or 0
    )

    # 3. Recent enrollments from database
    enrollments_db = (
        db.query(Enrollment)
        .order_by(Enrollment.enrolled_at.desc())
        .limit(20)
        .all()
    )
    enrollments_list: List[EnrollmentDetail] = []
    for enr in enrollments_db:
        enrollments_list.append(
            EnrollmentDetail(
                id=enr.id,
                planId=enr.plan_id,
                planName=enr.plan.name if enr.plan else "Membership Plan",
                price=int(enr.price),
                currency=enr.currency,
                name=enr.name,
                phone=enr.phone,
                email=enr.email or "",
                status=enr.status,
                enrolledAt=enr.enrolled_at.isoformat(),
            )
        )

    # 4. Recent contact inquiries from database
    contacts_db = (
        db.query(ContactInquiry)
        .order_by(ContactInquiry.created_at.desc())
        .limit(20)
        .all()
    )
    contacts_list: List[AdminContactItem] = []
    for c in contacts_db:
        contacts_list.append(
            AdminContactItem(
                id=c.id,
                submittedAt=c.created_at.isoformat(),
                name=c.name,
                phone=c.phone,
                email=c.email or "",
                message=c.message or "General inquiry",
                status=c.status,
            )
        )

    # 5. Operational Staff on Duty
    staff_roster = [
        StaffDutyItem(name="Coach Rohit V.", shift="6:00 AM - 2:00 PM", role="Head Coach"),
        StaffDutyItem(name="Coach Amit K.", shift="2:00 PM - 10:00 PM", role="Floor Coach"),
    ]

    # Audit log access
    audit = AuditLog(
        actor_id=user.id,
        action="admin.overview_viewed",
        resource_type="admin_dashboard",
        details={"operator_role": user.role},
    )
    db.add(audit)
    db.commit()

    return AdminOverviewResponse(
        totalMembers=total_members,
        activeTodayInGym=active_today,
        recentEnrollments=enrollments_list,
        recentContacts=contacts_list,
        staffDuty=staff_roster,
    )
