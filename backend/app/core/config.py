import os
import json
from typing import Any, List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Optional Email / Notification Settings
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAILS_FROM_EMAIL: str = "no-reply@rvfitness.in"

    def get_qr_signing_key(self) -> str:
        """Return dedicated QR signing key or fallback to main application secret key."""
        return (self.QR_SIGNING_KEY or self.SECRET_KEY).strip()

    def get_uploads_dir(self) -> str:
        """Resolve persistent uploads storage directory path."""
        if self.UPLOADS_DIR and self.UPLOADS_DIR.strip():
            return os.path.abspath(self.UPLOADS_DIR.strip())
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "uploads",
        )

    def is_cookie_secure(self) -> bool:
        """Determine if cookies should enforce the Secure attribute."""
        if self.COOKIE_SECURE is not None:
            return self.COOKIE_SECURE
        return self.ENVIRONMENT in {"production", "staging"}

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

        # QR Signing Key validation if explicitly set
        if settings_obj.QR_SIGNING_KEY:
            qr_key = settings_obj.QR_SIGNING_KEY.strip()
            if "change-this" in qr_key.lower() or len(qr_key) < 32:
                raise ValueError(
                    f"CRITICAL: In {env_label}, QR_SIGNING_KEY must be a secure string of at least 32 characters."
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
