import pytest
from pydantic import ValidationError
from backend.app.core.config import Settings


def test_production_rejects_sqlite():
    """Verify that production environment strictly forbids SQLite databases."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DATABASE_URL="sqlite:///./prod.db",
        )
    assert "SQLite is strictly forbidden in production" in str(exc_info.value)


def test_production_rejects_empty_database_url():
    """Verify that production environment requires a non-empty DATABASE_URL."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DATABASE_URL="",
        )
    assert "DATABASE_URL is required in production environment" in str(exc_info.value)


def test_production_accepts_valid_postgresql_url():
    """Verify that production environment accepts valid postgresql connection strings."""
    settings = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql://rvf_user:securepass@db.rvfitness.in:5432/rvf_prod",
    )
    assert settings.ENVIRONMENT == "production"
    assert settings.DATABASE_URL.startswith("postgresql://")


def test_invalid_environment_raises_validation_error():
    """Verify that an unrecognized environment name is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(ENVIRONMENT="staging_preview")
    assert "ENVIRONMENT must be one of" in str(exc_info.value)


def test_development_allows_sqlite_default():
    """Verify that development environment gracefully defaults to local SQLite."""
    settings = Settings(
        ENVIRONMENT="development",
        DATABASE_URL="sqlite:///./rvfitness_dev.db",
    )
    assert settings.ENVIRONMENT == "development"
    assert "sqlite" in settings.DATABASE_URL
