import os
import json
import re
from typing import Any, List, Optional
from urllib.parse import urlparse
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def sanitize_redis_url(url: Optional[str]) -> str:
    """Mask password credentials in Redis URL for safe logging and error reporting."""
    if not url:
        return "None"
    return re.sub(r"://([^:@/]*):([^@/]+)@", r"://\1:***@", str(url))


def validate_redis_url(url: Optional[str]) -> None:
    """
    Validate Redis URL scheme, hostname, and port before connection.
    Ensures malformed URLs are rejected early and credentials are redacted in errors.
    """
    if not url or not str(url).strip():
        raise ValueError("REDIS_URL cannot be empty.")

    clean_url = str(url).strip()
    sanitized = sanitize_redis_url(clean_url)

    clean_lower = clean_url.lower()
    if not (clean_lower.startswith("redis://") or clean_lower.startswith("rediss://")):
        raise ValueError(f"REDIS_URL must start with redis:// or rediss://, got '{sanitized}'.")

    try:
        parsed = urlparse(clean_url)
    except Exception as exc:
        raise ValueError(f"Invalid REDIS_URL '{sanitized}': malformed URL structure.") from exc

    if not parsed.hostname or not parsed.hostname.strip():
        raise ValueError(f"Invalid REDIS_URL '{sanitized}': hostname is required.")

    try:
        port = parsed.port
    except ValueError as pe:
        raise ValueError(f"Invalid REDIS_URL '{sanitized}': invalid port ({pe}).")

    if port is not None and not (1 <= port <= 65535):
        raise ValueError(f"Invalid REDIS_URL '{sanitized}': port must be between 1 and 65535.")


class Settings(BaseSettings):
    """Application configuration validated via Pydantic."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    PROJECT_NAME: str = "RVFitness Management Platform"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"

    # Environment: development | test | production
    ENVIRONMENT: str = "development"

    # Database Configuration
    DATABASE_URL: str = "sqlite:///./rvfitness_dev.db"

    # Security
    SECRET_KEY: str = "change-this-to-a-secure-random-64-character-hex-string-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5000",
        "http://127.0.0.1:5000",
    ]

    # Logging
    LOG_LEVEL: str = "INFO"

    # Database Connection Pool Configuration
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # Dedicated QR Signing Key (falls back to SECRET_KEY if None)
    QR_SIGNING_KEY: Optional[str] = None

    # Cookie Security Settings
    COOKIE_SECURE: Optional[bool] = None  # Auto-true in production
    COOKIE_SAMESITE: str = "lax"
    SESSION_COOKIE_NAME: str = "rvf_session"
    CSRF_COOKIE_NAME: str = "rvf_csrf_token"

    # Reverse Proxy & Trusted Proxy Configuration
    FORWARDED_ALLOW_IPS: str = "127.0.0.1,::1"
    TRUSTED_PROXIES: List[str] = ["127.0.0.1", "::1"]

    # Media & File Upload Configuration
    MAX_IMAGE_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MB
    UPLOADS_DIR: Optional[str] = None

    # Distributed Rate Limiting & Redis Configuration
    REDIS_URL: Optional[str] = None
    RATE_LIMITER_BACKEND: str = "auto"  # "auto" | "redis" | "memory"
    REDIS_CONNECT_TIMEOUT: float = 2.0
    REDIS_SOCKET_TIMEOUT: float = 2.0
    WORKERS_COUNT: int = 1

    # Optional Email / Notification Settings
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAILS_FROM_EMAIL: str = "no-reply@rvfitness.in"

    def get_qr_signing_key(self) -> str:
        """
        Return dedicated QR signing key.
        In staging and production, fallback to SECRET_KEY is forbidden; QR_SIGNING_KEY must be configured independently.
        """
        if self.ENVIRONMENT in {"production", "staging"}:
            qr_key = (self.QR_SIGNING_KEY or "").strip()
            if not qr_key:
                raise ValueError(
                    f"CRITICAL: In {self.ENVIRONMENT}, QR_SIGNING_KEY must be explicitly configured and cannot fall back to SECRET_KEY."
                )
            secret = (self.SECRET_KEY or "").strip()
            if qr_key == secret:
                raise ValueError(
                    f"CRITICAL: In {self.ENVIRONMENT}, QR_SIGNING_KEY must be distinct and independent from SECRET_KEY."
                )
            return qr_key
        return (self.QR_SIGNING_KEY or self.SECRET_KEY).strip()

    def get_uploads_dir(self) -> str:
        """
        Resolve persistent uploads storage directory path.
        If UPLOADS_DIR is explicitly configured, returns its absolute path.
        Otherwise:
        - In staging or production container environments with workdir /app: '/app/uploads'
        - In development or test: '<project_root>/backend/uploads'
        """
        if self.UPLOADS_DIR and self.UPLOADS_DIR.strip():
            return os.path.abspath(self.UPLOADS_DIR.strip())
        if self.ENVIRONMENT in {"staging", "production"} and os.path.isdir("/app"):
            return "/app/uploads"
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "uploads",
        )

    def is_cookie_secure(self) -> bool:
        """Determine if cookies should enforce the Secure attribute."""
        if self.COOKIE_SECURE is not None:
            return self.COOKIE_SECURE
        return self.ENVIRONMENT in {"production", "staging"}

    def get_sanitized_redis_url(self) -> Optional[str]:
        """Return REDIS_URL with password credentials masked."""
        if not self.REDIS_URL:
            return None
        return sanitize_redis_url(self.REDIS_URL)

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        valid_envs = {"development", "test", "staging", "production"}
        v_clean = v.strip().lower()
        if v_clean not in valid_envs:
            raise ValueError(f"ENVIRONMENT must be one of: {valid_envs}")
        return v_clean

    @field_validator("TRUSTED_PROXIES", mode="before")
    @classmethod
    def assemble_trusted_proxies(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed]
            except Exception:
                return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, tuple)):
            return [str(i).strip() for i in v]
        return ["127.0.0.1", "::1"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except Exception:
                return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, tuple)):
            return [str(i) for i in v]
        return ["http://localhost:5173", "http://127.0.0.1:5173"]

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str, info: Any) -> str:
        url = v.strip()
        env = info.data.get("ENVIRONMENT", "development")

        # Strict Production & Staging Enforcement: Never silently fall back to SQLite
        if env in {"production", "staging"}:
            if not url:
                raise ValueError(f"DATABASE_URL is required in {env} environment.")
            if "sqlite" in url.lower():
                raise ValueError(
                    f"SQLite is strictly forbidden in {env}. "
                    "A valid PostgreSQL connection string (postgresql://...) must be configured."
                )
            if not (
                url.startswith("postgresql://")
                or url.startswith("postgresql+psycopg2://")
                or url.startswith("postgres://")
            ):
                raise ValueError(
                    f"In {env}, DATABASE_URL must start with postgresql:// or postgresql+psycopg2://"
                )

        return url

settings = Settings()


def validate_production_security(settings_obj: Settings = settings) -> None:
    """
    Validate that critical production and staging security invariants are satisfied.
    Prevents deployment with default placeholder keys or insecure configurations.
    """
    if settings_obj.ENVIRONMENT in {"production", "staging"}:
        env_label = settings_obj.ENVIRONMENT
        key = (settings_obj.SECRET_KEY or "").strip()
        if not key or "change-this" in key.lower() or len(key) < 32:
            raise ValueError(
                f"CRITICAL: In {env_label}, SECRET_KEY must be a cryptographically secure random string of at least 32 characters."
            )

        # Check for predictable weak patterns
        weak_patterns = ["password", "secret123", "default_key", "admin123"]
        if any(w in key.lower() for w in weak_patterns) and len(set(key)) < 12:
            raise ValueError(
                f"CRITICAL: In {env_label}, SECRET_KEY contains predictable or low-entropy patterns."
            )

        # Dedicated QR Signing Key enforcement in staging and production
        qr_key = (settings_obj.QR_SIGNING_KEY or "").strip()
        if not qr_key:
            raise ValueError(
                f"CRITICAL: In {env_label}, QR_SIGNING_KEY must be explicitly configured and cannot be omitted or empty."
            )
        if "change-this" in qr_key.lower():
            raise ValueError(
                f"CRITICAL: In {env_label}, QR_SIGNING_KEY must not use default or placeholder values."
            )
        if len(qr_key) < 32:
            raise ValueError(
                f"CRITICAL: In {env_label}, QR_SIGNING_KEY must be a secure string of at least 32 characters."
            )
        if qr_key == key:
            raise ValueError(
                f"CRITICAL: In {env_label}, QR_SIGNING_KEY must be distinct and independent from SECRET_KEY."
            )
        if any(w in qr_key.lower() for w in weak_patterns) and len(set(qr_key)) < 12:
            raise ValueError(
                f"CRITICAL: In {env_label}, QR_SIGNING_KEY contains predictable or low-entropy patterns."
            )

        # Wildcard CORS validation
        if "*" in settings_obj.CORS_ORIGINS:
            raise ValueError(f"CRITICAL: Wildcard CORS origin ('*') is strictly forbidden in {env_label}.")

        # Cookie Security enforcement
        if settings_obj.COOKIE_SECURE is False:
            raise ValueError(f"CRITICAL: In {env_label}, COOKIE_SECURE cannot be explicitly disabled.")

        # CSRF cookie name enforcement to prevent silent frontend divergence
        if settings_obj.CSRF_COOKIE_NAME != "rvf_csrf_token":
            raise ValueError(
                f"CRITICAL: CSRF_COOKIE_NAME is configured as '{settings_obj.CSRF_COOKIE_NAME}', "
                "which diverges from the frontend client expectation 'rvf_csrf_token'. "
                "CSRF cookie name must be 'rvf_csrf_token' to prevent silent authentication failure."
            )

        # Media storage directory verification in staging and production
        uploads_dir = settings_obj.get_uploads_dir()
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        if settings_obj.UPLOADS_DIR and settings_obj.UPLOADS_DIR.strip():
            # Verify uploads directory is not located inside the application source tree
            try:
                up_drive, _ = os.path.splitdrive(os.path.abspath(uploads_dir))
                bk_drive, _ = os.path.splitdrive(os.path.abspath(backend_dir))
                if not up_drive or up_drive.lower() == bk_drive.lower():
                    common = os.path.commonpath([os.path.abspath(uploads_dir), os.path.abspath(backend_dir)])
                    if common == os.path.abspath(backend_dir):
                        raise ValueError(
                            f"CRITICAL: In {env_label}, media uploads directory cannot be located inside the application source tree: '{uploads_dir}'. "
                            "Configure UPLOADS_DIR to a dedicated persistent volume mount (e.g., /app/uploads)."
                        )
            except ValueError as ve:
                if "don't have the same drive" not in str(ve).lower() and "different drive" not in str(ve).lower():
                    raise

            # Verify directory existence and write permissions
            try:
                target_sub = os.path.join(uploads_dir, "announcements")
                os.makedirs(target_sub, exist_ok=True)
                probe_path = os.path.join(target_sub, ".rw_probe")
                with open(probe_path, "w", encoding="utf-8") as f:
                    f.write("probe")
                if os.path.exists(probe_path):
                    os.remove(probe_path)
            except Exception as exc:
                raise ValueError(
                    f"CRITICAL: In {env_label}, media storage directory '{uploads_dir}' is unusable or not writable: {exc}"
                )
        elif os.path.isdir("/app"):
            raise ValueError(
                f"CRITICAL: In {env_label} container environment, UPLOADS_DIR must be explicitly configured to a persistent volume mount."
            )

        # Distributed Rate Limiting validation in staging and production
        backend_mode = settings_obj.RATE_LIMITER_BACKEND.lower().strip()
        if backend_mode not in {"auto", "redis", "memory"}:
            raise ValueError(
                f"CRITICAL: RATE_LIMITER_BACKEND must be one of 'auto', 'redis', or 'memory', got '{settings_obj.RATE_LIMITER_BACKEND}'."
            )

        if backend_mode == "memory":
            raise ValueError(
                f"CRITICAL: In {env_label}, in-memory rate limiting is strictly forbidden. "
                "Distributed rate limiting via Redis is required regardless of worker count. "
                "Set RATE_LIMITER_BACKEND to 'redis' (or 'auto') and configure REDIS_URL."
            )

        if not settings_obj.REDIS_URL or not settings_obj.REDIS_URL.strip():
            raise ValueError(
                f"CRITICAL: In {env_label}, REDIS_URL must be configured to support distributed rate limiting."
            )

        try:
            validate_redis_url(settings_obj.REDIS_URL)
        except ValueError as exc:
            raise ValueError(f"CRITICAL: In {env_label}, {exc}") from exc
