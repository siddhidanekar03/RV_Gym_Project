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
from backend.app.api.v1.endpoints.enrollment import build_enrollment_detail

router = APIRouter()


@router.get(
    "/admin/overview",
    response_model=AdminOverviewResponse,
    dependencies=[Depends(require_roles("org_admin", "admin", "branch_manager", "manager", "front_desk", "staff"))],
    summary="Staff Operations Desk Overview",
)
def get_admin_overview(
    user: User = Depends(require_roles("org_admin", "admin", "branch_manager", "manager", "front_desk", "staff")),
    db: Session = Depends(get_db),
) -> AdminOverviewResponse:
    today = date.today()
    is_org_wide = user.role in ("org_admin", "admin")

    # 1. Truthful member count (active members in the database)
    member_q = db.query(func.count(User.id)).filter(User.role == "member", User.is_active == True)
    if not is_org_wide and user.branch_id:
        member_q = member_q.filter(User.branch_id == user.branch_id)
    total_members = member_q.scalar() or 0

    # 2. Truthful active today count (actual check-in records recorded today)
    attendance_q = db.query(func.count(func.distinct(AttendanceRecord.user_id))).filter(AttendanceRecord.check_in_date == today)
    if not is_org_wide and user.branch_id:
        attendance_q = attendance_q.filter(AttendanceRecord.branch_id == user.branch_id)
    active_today = attendance_q.scalar() or 0

    # 3. Recent enrollments from database
    enrollment_q = db.query(Enrollment)
    if not is_org_wide and user.branch_id:
        enrollment_q = enrollment_q.filter(Enrollment.branch_id == user.branch_id)
    enrollments_db = (
        enrollment_q
        .order_by(Enrollment.enrolled_at.desc())
        .limit(20)
        .all()
    )
    enrollments_list = [build_enrollment_detail(enr, db) for enr in enrollments_db]

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
