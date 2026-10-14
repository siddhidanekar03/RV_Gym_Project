import hashlib
import hmac
import secrets
import bcrypt


def hash_password(password: str) -> str:
    """Hash password using bcrypt with salt."""
    if not password:
        raise ValueError("Password cannot be empty")
    salt = bcrypt.gensalt(rounds=12)
    # Truncate to 72 bytes per bcrypt standard to avoid wrap issues
    pw_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against stored bcrypt hash using constant-time comparison."""
    if not plain_password or not hashed_password:
        return False
    try:
        pw_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pw_bytes, hash_bytes)
    except Exception:
        return False


def generate_session_token() -> str:
    """Generate a high-entropy cryptographically secure random session token."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Compute SHA-256 hash of a session token for secure database storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_urlsafe(32)


def verify_csrf_token(provided_token: str, expected_token: str) -> bool:
    """Verify CSRF token using constant-time comparison."""
    if not provided_token or not expected_token:
        return False
    return hmac.compare_digest(provided_token.strip(), expected_token.strip())
