from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional, Callable, Sequence, Any
from fastapi import Request, Response, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.security import (
    generate_session_token,
    hash_session_token,
    generate_csrf_token,
    verify_csrf_token,
)
from backend.app.models.session import UserSession
from backend.app.models.user import User

SESSION_COOKIE_NAME = "rvf_session"
CSRF_COOKIE_NAME = "rvf_csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"


def get_client_ip(request: Optional[Any] = None) -> Optional[str]:
    if not request:
        return None
    headers = getattr(request, "headers", None)
    if headers and hasattr(headers, "get"):
        forwarded = headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    client_obj = getattr(request, "client", None)
    if client_obj and hasattr(client_obj, "host"):
        return client_obj.host
    return None


def create_user_session(
    db: Session,
    user: User,
    request: Optional[Any] = None,
) -> Tuple[UserSession, str, str]:
    """
    Create a new database-backed session for the user and return
    (session_record, raw_session_token, raw_csrf_token).
    """
    raw_session_token = generate_session_token()
    token_hash = hash_session_token(raw_session_token)
    raw_csrf_token = generate_csrf_token()

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    user_agent = ""
    if request:
        headers = getattr(request, "headers", None)
        if headers and hasattr(headers, "get"):
            user_agent = (headers.get("user-agent") or "")[:255]

    session = UserSession(
        user_id=user.id,
        session_token_hash=token_hash,
        csrf_token=raw_csrf_token,
        ip_address=get_client_ip(request),
        user_agent=user_agent,
        is_revoked=False,
        expires_at=expires_at,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return session, raw_session_token, raw_csrf_token


def set_auth_cookies(
    response: Response,
    raw_session_token: str,
    raw_csrf_token: str,
) -> None:
    """Set secure HttpOnly session cookie and readable CSRF cookie."""
    is_prod = settings.ENVIRONMENT == "production"
    max_age_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    # 1. HttpOnly signed session cookie
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_session_token,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        path="/",
        max_age=max_age_seconds,
    )

    # 2. Readable CSRF cookie for client header submission
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=raw_csrf_token,
        httponly=False,
        secure=is_prod,
        samesite="lax",
        path="/",
        max_age=max_age_seconds,
    )


def clear_auth_cookies(response: Response) -> None:
    """Clear session and CSRF cookies."""
    is_prod = settings.ENVIRONMENT == "production"
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=is_prod,
        samesite="lax",
    )
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path="/",
        httponly=False,
        secure=is_prod,
        samesite="lax",
    )


def get_current_session(
    request: Request,
    db: Session = Depends(get_db),
) -> UserSession:
    """
    Dependency that extracts and validates the active server-side session.
    Checks cookie, revocation state, and expiration.
    """
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)

    # Fallback to Authorization: Bearer <token> for programmatic clients / testing
    if not raw_token:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_token = auth_header[7:].strip()

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Missing session credentials.",
        )

    token_hash = hash_session_token(raw_token)
    session = (
        db.query(UserSession)
        .filter(UserSession.session_token_hash == token_hash)
        .first()
    )

    if not session or session.is_revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is invalid or has been revoked. Please sign in again.",
        )

    now = datetime.now(timezone.utc)
    # Ensure timezone awareness on comparison
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now:
        session.is_revoked = True
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired. Please sign in again.",
        )

    return session


def get_current_user(
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> User:
    """Dependency that resolves the authenticated User entity from the active session."""
    user = db.query(User).filter(User.id == session.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account associated with this session no longer exists.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been suspended or deactivated. Contact gym management.",
        )

    return user


def require_csrf(
    request: Request,
    session: UserSession = Depends(get_current_session),
) -> None:
    """
    CSRF verification dependency for state-changing requests (POST, PUT, DELETE, PATCH).
    Validates X-CSRF-Token header against session.csrf_token.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    provided_token = request.headers.get(CSRF_HEADER_NAME)
    if not provided_token or not verify_csrf_token(provided_token, session.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed. Missing or invalid X-CSRF-Token header.",
        )


ROLE_ALIASES = {
    "org_admin": {"org_admin", "admin"},
    "admin": {"org_admin", "admin"},
    "branch_manager": {"branch_manager", "manager"},
    "manager": {"branch_manager", "manager"},
    "front_desk": {"front_desk", "staff"},
    "staff": {"front_desk", "staff"},
    "trainer": {"trainer"},
    "member": {"member"},
}


def require_roles(*allowed_roles: str) -> Callable:
    """
    Role-Based Access Control (RBAC) dependency factory.
    Roles: 'org_admin'/'admin', 'branch_manager'/'manager', 'front_desk'/'staff', 'trainer', 'member'.
    """
    expanded_allowed = set()
    for role in allowed_roles:
        expanded_allowed.update(ROLE_ALIASES.get(role, {role}))

    def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in expanded_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Insufficient role permissions for this operation.",
            )
        return user

    return role_checker


def verify_branch_access(user: User, target_branch_id: str) -> None:
    """
    Enforce branch-scoped isolation for branch managers and front desk staff.
    Organization Admins have multi-branch administrative authority.
    """
    if user.role in ("org_admin", "admin"):
        return
    if user.role in ("branch_manager", "manager", "front_desk", "staff"):
        if user.branch_id != target_branch_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Your administrative scope is restricted to your assigned branch.",
            )
        return
    if user.role == "member":
        if user.branch_id != target_branch_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Operation outside your member branch scope.",
            )
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
