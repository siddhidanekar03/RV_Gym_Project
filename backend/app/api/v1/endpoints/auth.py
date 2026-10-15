import random
from datetime import date, datetime, timezone
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.security import hash_password, verify_password, generate_csrf_token
from backend.app.core.rate_limit import rate_limit
from backend.app.core.auth import (
    create_user_session,
    set_auth_cookies,
    clear_auth_cookies,
    get_current_session,
    get_current_user,
    require_csrf,
    SESSION_COOKIE_NAME,
    CSRF_COOKIE_NAME,
)
from backend.app.models.user import User
from backend.app.models.attendance import AttendanceRecord
from backend.app.models.personal_record import PersonalRecord
from backend.app.models.audit import AuditLog
from backend.app.services.attendance_service import reconcile_member_identity_on_account_link
from backend.app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    AuthResponse,
    SafeUserResponse,
    LogoutResponse,
    CsrfResponse,
)

router = APIRouter()


def build_safe_user(user: User, db: Session) -> SafeUserResponse:
    """Construct sanitized user payload with verified database attendance and PRs."""
    today = date.today()
    first_of_month = date(today.year, today.month, 1)

    # 1. Real database count of sessions this calendar month
    monthly_visits = (
        db.query(func.count(AttendanceRecord.id))
        .filter(
            AttendanceRecord.user_id == user.id,
            AttendanceRecord.check_in_date >= first_of_month,
        )
        .scalar()
        or 0
    )

    # 2. Real check if checked in today
    today_checkin = (
        db.query(AttendanceRecord.id)
        .filter(
            AttendanceRecord.user_id == user.id,
            AttendanceRecord.check_in_date == today,
        )
        .first()
        is not None
    )

    # 3. Verified PRs from database
    prs_records = (
        db.query(PersonalRecord)
        .filter(PersonalRecord.user_id == user.id)
        .all()
    )
    prs_dict: Dict[str, str] = {}
    for p in prs_records:
        prs_dict[p.exercise_name] = f"{int(p.value) if p.value % 1 == 0 else p.value} {p.unit}"

    if not prs_dict and user.role == "member":
        prs_dict = {
            "benchPress": "Pending Assessment",
            "squat": "Pending Assessment",
            "deadlift": "Pending Assessment",
            "pullUps": "Pending Assessment",
        }

    # 4. Recent attendance history dates
    history_records = (
        db.query(AttendanceRecord.check_in_date)
        .filter(AttendanceRecord.user_id == user.id)
        .order_by(AttendanceRecord.check_in_date.desc())
        .limit(30)
        .all()
    )
    history_dates = [d[0].isoformat() for d in history_records]

    # Assigned coach details
    assigned_trainer_name = user.assigned_trainer.name if user.assigned_trainer else "Coach Rohit V."

    plan_name = user.membership_plan.name if user.membership_plan else (
        "Quarterly" if user.membership_status == "active" else "Trial / Awaiting Activation"
    )

    return SafeUserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        phone=user.phone,
        role=user.role,
        staffRole=user.staff_role,
        branchId=user.branch_id,
        membershipId=user.membership_id,
        membershipPlan=plan_name,
        memberSince=user.member_since.strftime("%B %Y") if user.member_since else "Recent",
        validUntil=user.valid_until.strftime("%B %d, %Y") if user.valid_until else "Pending Activation",
        status=user.membership_status.capitalize(),
        streakDays=user.streak_days,
        attendanceThisMonth=monthly_visits,
        todayCheckedIn=today_checkin,
        prs=prs_dict,
        assignedPlan={
            "trainer": assigned_trainer_name,
            "split": "Upper / Lower Strength & Hypertrophy" if user.role == "member" else "Staff Protocol",
            "todayFocus": "Compound Strength & Core Stability",
        },
        attendanceHistory=history_dates,
    )


@router.post(
    "/auth/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit(max_requests=5, window_seconds=60))],
    summary="Register New Member Account",
)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    if not payload.acceptedTerms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must accept the Terms of Service and Privacy Policy to register.",
        )

    clean_email = payload.email.strip().lower()
    existing = db.query(User).filter(User.email == clean_email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    # Use existing offline membership card if provided, or generate unique RVF-YYYY-XXX
    if payload.membershipId and payload.membershipId.strip():
        membership_code = payload.membershipId.strip().upper()
        existing_card_user = db.query(User).filter(User.membership_id == membership_code).first()
        if existing_card_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Membership card '{membership_code}' is already linked to another registered account.",
            )
    else:
        year = date.today().year
        rand_code = random.randint(100, 999)
        membership_code = f"RVF-{year}-{rand_code}"
        while db.query(User).filter(User.membership_id == membership_code).first():
            rand_code = random.randint(100, 999)
            membership_code = f"RVF-{year}-{rand_code}"

    hashed = hash_password(payload.password)
    new_user = User(
        email=clean_email,
        hashed_password=hashed,
        name=payload.name.strip(),
        phone=(payload.phone or "").strip() or None,
        role="member",
        membership_id=membership_code,
        membership_status="pending",
        streak_days=0,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Reconcile any pre-existing unlinked offline attendance records or attempts
    reconcile_member_identity_on_account_link(db=db, user=new_user)

    # Establish server-side session
    session, raw_token, csrf_token = create_user_session(db, new_user, request)
    set_auth_cookies(response, raw_token, csrf_token)

    # Log audit event
    audit = AuditLog(
        actor_id=new_user.id,
        action="auth.register",
        resource_type="user",
        resource_id=new_user.id,
        details={"email": clean_email, "role": new_user.role},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit)
    db.commit()

    safe_user = build_safe_user(new_user, db)
    return AuthResponse(
        user=safe_user,
        message="Registration successful! Welcome to RVFitness.",
        csrfToken=csrf_token,
    )


@router.post(
    "/auth/login",
    response_model=AuthResponse,
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60))],
    summary="Sign In with Credentials",
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    clean_email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == clean_email).first()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Please contact gym administration.",
        )

    session, raw_token, csrf_token = create_user_session(db, user, request)
    set_auth_cookies(response, raw_token, csrf_token)

    # Log audit event
    audit = AuditLog(
        actor_id=user.id,
        action="auth.login",
        resource_type="user",
        resource_id=user.id,
        details={"email": clean_email, "role": user.role},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit)
    db.commit()

    safe_user = build_safe_user(user, db)
    return AuthResponse(
        user=safe_user,
        message=f"Welcome back, {user.name}!",
        csrfToken=csrf_token,
    )


@router.get("/auth/me", summary="Get Current Authenticated User Profile")
def get_me(
    response: Response,
    user: User = Depends(get_current_user),
    session=Depends(get_current_session),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    safe_user = build_safe_user(user, db)
    # Ensure CSRF cookie is synchronized
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=session.csrf_token,
        httponly=False,
        secure=settings.is_cookie_secure(),
        samesite="lax",
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return {"user": safe_user.model_dump(), "csrfToken": session.csrf_token}


@router.post(
    "/auth/logout",
    response_model=LogoutResponse,
    dependencies=[Depends(require_csrf)],
    summary="Sign Out and Invalidate Session",
)
def logout(
    response: Response,
    session=Depends(get_current_session),
    db: Session = Depends(get_db),
) -> LogoutResponse:
    session.is_revoked = True
    db.commit()
    clear_auth_cookies(response)

    # Audit log
    audit = AuditLog(
        actor_id=session.user_id,
        action="auth.logout",
        resource_type="user_session",
        resource_id=session.id,
        details={"status": "revoked"},
    )
    db.add(audit)
    db.commit()

    return LogoutResponse(success=True, message="Logged out successfully.")


@router.get("/auth/csrf", response_model=CsrfResponse, summary="Retrieve or Refresh CSRF Token")
def get_csrf(request: Request, response: Response, db: Session = Depends(get_db)) -> CsrfResponse:
    """Retrieve active session CSRF token or generate a pre-auth CSRF token."""
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    csrf_val = None

    if raw_token:
        try:
            session = get_current_session(request, db)
            csrf_val = session.csrf_token
        except HTTPException:
            csrf_val = None

    if not csrf_val:
        csrf_val = generate_csrf_token()

    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_val,
        httponly=False,
        secure=settings.is_cookie_secure(),
        samesite="lax",
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return CsrfResponse(csrfToken=csrf_val)
