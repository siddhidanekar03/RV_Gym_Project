"""
Fail-Closed Staging Database Target Verification Tool.

Guarantees that database migrations can only execute against an authenticated,
explicitly approved staging PostgreSQL instance.
Resolves database target using the identical configuration precedence as Alembic env.py.
"""
import os
import sys
from urllib.parse import urlparse
from typing import Dict, Any, Optional, Callable, List


def get_alembic_ini_url() -> Optional[str]:
    """Inspect alembic.ini or backend/alembic.ini for an explicitly configured sqlalchemy.url."""
    import configparser
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    custom_ini = os.environ.get("ALEMBIC_CONFIG")
    candidates = [custom_ini] if custom_ini else []
    candidates.extend([
        os.path.join(repo_root, "alembic.ini"),
        os.path.join(repo_root, "backend", "alembic.ini"),
        "alembic.ini",
        "backend/alembic.ini",
    ])

    for ini_path in candidates:
        if ini_path and os.path.isfile(ini_path):
            parser = configparser.ConfigParser()
            try:
                parser.read(ini_path)
                if parser.has_section("alembic") and parser.has_option("alembic", "sqlalchemy.url"):
                    val = parser.get("alembic", "sqlalchemy.url").strip()
                    if val:
                        return val
            except Exception:
                pass
    return None


def get_effective_alembic_url() -> str:
    """
    Resolve the effective database URL using the exact configuration precedence as alembic/env.py.
    Fails closed if conflicting or ambiguous URLs are detected across configuration sources.
    """
    ini_url = get_alembic_ini_url()
    test_pg = os.environ.get("POSTGRESQL_TEST_URL")
    db_url = os.environ.get("DATABASE_URL")
    test_db = os.environ.get("TEST_DATABASE_URL")

    # Collect all populated explicit URL sources to check for conflicting settings
    explicit_sources: Dict[str, str] = {}
    if ini_url:
        explicit_sources["alembic.ini (sqlalchemy.url)"] = ini_url.strip()
    if test_pg:
        explicit_sources["POSTGRESQL_TEST_URL"] = test_pg.strip()
    if db_url:
        explicit_sources["DATABASE_URL"] = db_url.strip()
    if test_db:
        explicit_sources["TEST_DATABASE_URL"] = test_db.strip()

    # Ambiguity check: if multiple explicit sources exist and their target URLs differ, fail closed
    if len(explicit_sources) > 1:
        distinct_urls = set(explicit_sources.values())
        if len(distinct_urls) > 1:
            sources_summary = ", ".join(f"{k}='{sanitize_db_url(v)}'" for k, v in explicit_sources.items())
            raise ValueError(
                f"Ambiguous database configuration: conflicting connection strings detected across multiple sources: {sources_summary}. "
                "Ensure only one target URL is specified or that all sources match identically."
            )

    # Precedence: ini_url -> POSTGRESQL_TEST_URL -> DATABASE_URL -> TEST_DATABASE_URL -> settings.DATABASE_URL
    effective = ini_url or test_pg or db_url or test_db
    if not effective:
        from backend.app.core.config import settings
        effective = settings.DATABASE_URL

    return (effective or "").strip()


def sanitize_db_url(url: str) -> str:
    """Mask credentials in database URL for safe logging and diagnostics."""
    if not url:
        return "<empty>"
    try:
        parsed = urlparse(url)
        netloc = ""
        if parsed.username:
            netloc += parsed.username
            if parsed.password:
                netloc += ":***"
            netloc += "@"
        netloc += parsed.hostname or "unknown_host"
        if parsed.port:
            netloc += f":{parsed.port}"
        return f"{parsed.scheme}://{netloc}{parsed.path}"
    except Exception:
        return "<malformed_url>"


def run_target_verification(
    connector: Optional[Callable[[str], Dict[str, Any]]] = None,
    expected_env: str = "staging",
    expected_db: Optional[str] = None,
    expected_user: Optional[str] = None,
    approved_hosts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Execute fail-closed validation of staging migration target.

    Raises ValueError on any safety violation.
    Returns verified connection metadata dictionary on success.
    """
    current_env = os.environ.get("ENVIRONMENT", "").strip().lower()
    if current_env != expected_env:
        raise ValueError(
            f"Pre-migration check failed: ENVIRONMENT must be strictly '{expected_env}'. "
            f"Current value is '{current_env or '<unset>'}'. Migrations aborted."
        )

    effective_url = get_effective_alembic_url()
    if not effective_url:
        raise ValueError("Pre-migration check failed: No effective database URL could be resolved.")

    if "sqlite" in effective_url.lower():
        raise ValueError(
            "Pre-migration check failed: SQLite database detected. "
            "Staging migrations strictly require a PostgreSQL database."
        )

    parsed = urlparse(effective_url)
    if parsed.scheme not in ("postgresql", "postgresql+psycopg2", "postgres"):
        raise ValueError(
            f"Pre-migration check failed: Unsupported database scheme '{parsed.scheme}'. "
            "Must be postgresql or postgresql+psycopg2."
        )

    target_host = (parsed.hostname or "").strip().lower()
    url_db_name = (parsed.path or "").lstrip("/")

    # Explicit expected target resolution
    target_expected_db = (
        expected_db
        or os.environ.get("EXPECTED_STAGING_DB_NAME")
        or "rvfitness_staging"
    ).strip()

    target_expected_user = (
        expected_user
        or os.environ.get("EXPECTED_STAGING_USER")
        or os.environ.get("EXPECTED_STAGING_DB_USER")
        or "rvf_staging_migrator"
    ).strip()

    # Approved hosts resolution: must be explicitly provided via argument or APPROVED_STAGING_HOSTS env
    target_approved_hosts = approved_hosts
    if target_approved_hosts is None:
        raw_hosts = os.environ.get("APPROVED_STAGING_HOSTS", "").strip()
        if raw_hosts:
            target_approved_hosts = [h.strip().lower() for h in raw_hosts.split(",") if h.strip()]
        else:
            raise ValueError(
                "Pre-migration check failed: APPROVED_STAGING_HOSTS must be explicitly configured. "
                "Specify approved staging hostnames or network addresses (e.g. APPROVED_STAGING_HOSTS=staging-db.internal,10.0.1.5)."
            )

    if target_host not in target_approved_hosts:
        raise ValueError(
            f"Pre-migration check failed: Database host '{target_host}' is not in approved staging hosts list "
            f"{target_approved_hosts}. Aborting migration to unverified host."
        )

    if url_db_name != target_expected_db:
        raise ValueError(
            f"Pre-migration check failed: Target database name in URL is '{url_db_name}', "
            f"which does not match expected staging database '{target_expected_db}'."
        )

    sanitized = sanitize_db_url(effective_url)

    # Live connection inspection
    if connector is None:
        def default_connector(raw_url: str) -> Dict[str, Any]:
            import psycopg2
            dsn = raw_url.replace("postgresql+psycopg2://", "postgresql://")
            conn = psycopg2.connect(dsn)
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT current_database(), current_user, inet_server_addr()::text;")
                    actual_db, actual_user, server_ip = cur.fetchone()
                    return {
                        "database": str(actual_db),
                        "user": str(actual_user),
                        "server_ip": str(server_ip) if server_ip else target_host,
                    }
            finally:
                conn.close()

        connector = default_connector

    try:
        live_meta = connector(effective_url)
    except Exception as exc:
        raise ValueError(f"Pre-migration check failed: Could not connect to target database: {exc}") from exc

    actual_db = live_meta.get("database", "").strip()
    actual_user = live_meta.get("user", "").strip()
    server_ip = (live_meta.get("server_ip") or "").strip().lower()

    if actual_db != target_expected_db:
        raise ValueError(
            f"Pre-migration check failed: Connected catalog is '{actual_db}', "
            f"expected '{target_expected_db}'."
        )

    if target_expected_user and actual_user != target_expected_user:
        raise ValueError(
            f"Pre-migration check failed: Connected user role is '{actual_user}', "
            f"expected privileged migrator role '{target_expected_user}'."
        )

    # Server network identity verification beyond database name
    if server_ip and server_ip != target_host and server_ip not in target_approved_hosts:
        raise ValueError(
            f"Pre-migration check failed: Connected server network address '{server_ip}' "
            f"is not in approved staging hosts list {target_approved_hosts}."
        )

    return {
        "status": "verified",
        "sanitized_url": sanitized,
        "database": actual_db,
        "user": actual_user,
        "host": target_host,
        "server_ip": server_ip or target_host,
    }


def main():
    """CLI Entrypoint for pre-migration guard."""
    try:
        result = run_target_verification()
        print("==============================================================================")
        print("STAGING MIGRATION TARGET VERIFICATION: PASSED")
        print(f"Target Database : {result['database']}")
        print(f"Connected User  : {result['user']}")
        print(f"Host / Server   : {result['host']} ({result.get('server_ip')})")
        print(f"Sanitized DSN   : {result['sanitized_url']}")
        print("==============================================================================")
        sys.exit(0)
    except Exception as exc:
        print("==============================================================================", file=sys.stderr)
        print("STAGING MIGRATION TARGET VERIFICATION: FAILED", file=sys.stderr)
        print(f"Error: {exc}", file=sys.stderr)
        print("==============================================================================", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
