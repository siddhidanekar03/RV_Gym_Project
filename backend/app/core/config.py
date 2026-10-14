import json
from typing import Any, List
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

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        valid_envs = {"development", "test", "production"}
        v_clean = v.strip().lower()
        if v_clean not in valid_envs:
            raise ValueError(f"ENVIRONMENT must be one of: {valid_envs}")
        return v_clean

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

        # Strict Production Enforcement: Never silently fall back to SQLite
        if env == "production":
            if not url:
                raise ValueError("DATABASE_URL is required in production environment.")
            if "sqlite" in url.lower():
                raise ValueError(
                    "SQLite is strictly forbidden in production. "
                    "A valid PostgreSQL connection string (postgresql://...) must be configured."
                )
            if not (
                url.startswith("postgresql://")
                or url.startswith("postgresql+psycopg2://")
                or url.startswith("postgres://")
            ):
                raise ValueError(
                    "In production, DATABASE_URL must start with postgresql:// or postgresql+psycopg2://"
                )

        return url


settings = Settings()
