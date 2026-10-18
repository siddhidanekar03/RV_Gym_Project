"""
Fail-Closed Production Database Target Verification Tool.

Guarantees that database migrations can only execute against an authenticated,
explicitly approved production PostgreSQL instance.
Rejects staging, test, smoke, and development databases unconditionally.
Resolves database target using the identical configuration precedence as Alembic env.py.
"""
import os
import sys
import socket
from urllib.parse import urlparse
from typing import Dict, Any, Optional, Callable, List

FORBIDDEN_PROD_KEYWORDS = ["staging", "test", "smoke", "dev", "mock", "sandbox", "disposable"]


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


def get_effective_alembic_url() -> str:
    """
    Resolve effective database URL using exact configuration precedence as alembic/env.py.
    Fails closed if conflicting or ambiguous URLs are detected across configuration sources.
    """
    ini_url = get_alembic_ini_url()
    test_pg = os.environ.get("POSTGRESQL_TEST_URL")
    db_url = os.environ.get("DATABASE_URL")
    test_db = os.environ.get("TEST_DATABASE_URL")

    explicit_sources: Dict[str, str] = {}
    if ini_url:
        explicit_sources["alembic.ini (sqlalchemy.url)"] = ini_url.strip()
    if test_pg:
        explicit_sources["POSTGRESQL_TEST_URL"] = test_pg.strip()
    if db_url:
        explicit_sources["DATABASE_URL"] = db_url.strip()
    if test_db:
        explicit_sources["TEST_DATABASE_URL"] = test_db.strip()

    if len(explicit_sources) > 1:
        distinct_urls = set(explicit_sources.values())
        if len(distinct_urls) > 1:
            sources_summary = ", ".join(f"{k}='{sanitize_db_url(v)}'" for k, v in explicit_sources.items())
            raise ValueError(
                f"Ambiguous database configuration: conflicting connection strings detected: {sources_summary}. "
                "Ensure only one target URL is specified or all sources match identically."
            )

    effective = ini_url or test_pg or db_url or test_db
    if not effective:
        from backend.app.core.config import settings
        effective = settings.DATABASE_URL

    return (effective or "").strip()


def run_production_target_verification(
    connector: Optional[Callable[[str], Dict[str, Any]]] = None,
    expected_env: str = "production",
    expected_db: Optional[str] = None,
    expected_user: Optional[str] = None,
    approved_hosts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Execute fail-closed validation of production migration target.
    Raises ValueError on any safety violation.
    Returns verified connection metadata dictionary on success.
    """
    current_env = os.environ.get("ENVIRONMENT", "").strip().lower()
    if current_env != expected_env:
        raise ValueError(
            f"Pre-migration check failed: ENVIRONMENT must be strictly '{expected_env}'. "
            f"Current value is '{current_env or '<unset>'}'. Production migrations aborted."
        )

    effective_url = get_effective_alembic_url()
    if not effective_url:
        raise ValueError("Pre-migration check failed: No effective database URL could be resolved.")

    if "sqlite" in effective_url.lower():
        raise ValueError(
            "Pre-migration check failed: SQLite database detected. "
            "Production strictly requires an authenticated PostgreSQL instance."
        )

    parsed = urlparse(effective_url)
    if parsed.scheme not in ("postgresql", "postgresql+psycopg2", "postgres"):
        raise ValueError(
            f"Pre-migration check failed: Unsupported database scheme '{parsed.scheme}'. "
            "Must be postgresql or postgresql+psycopg2."
        )

    target_host = (parsed.hostname or "").strip().lower()
    url_db_name = (parsed.path or "").lstrip("/").strip().lower()

    # Reject forbidden non-production keywords in host and database name
    for kw in FORBIDDEN_PROD_KEYWORDS:
        if kw in url_db_name:
            raise ValueError(
                f"SAFETY VIOLATION: Database name '{url_db_name}' contains non-production keyword '{kw}'. "
                "Production migrations are forbidden on staging, test, smoke, or development databases."
            )
        if kw in target_host:
            raise ValueError(
                f"SAFETY VIOLATION: Database host '{target_host}' contains non-production keyword '{kw}'. "
                "Production migrations are forbidden on non-production hosts."
            )

    # Resolve expected target DB and user
    target_expected_db = (
        expected_db
        or os.environ.get("EXPECTED_PROD_DB_NAME")
        or "rvfitness_prod"
    ).strip().lower()

    target_expected_user = (
        expected_user
        or os.environ.get("EXPECTED_PROD_USER")
        or "rvf_migrator"
    ).strip()

    # Approved production hosts resolution
    target_approved_hosts = approved_hosts
    if target_approved_hosts is None:
        raw_hosts = os.environ.get("APPROVED_PROD_HOSTS", "").strip()
        if raw_hosts:
            target_approved_hosts = [h.strip().lower() for h in raw_hosts.split(",") if h.strip()]
        else:
            raise ValueError(
                "Pre-migration check failed: APPROVED_PROD_HOSTS must be explicitly configured. "
                "Specify approved production hostnames or network addresses (e.g. APPROVED_PROD_HOSTS=prod-db,10.0.2.5)."
            )

    if target_host not in target_approved_hosts:
        raise ValueError(
            f"Pre-migration check failed: Database host '{target_host}' is not in approved production hosts list "
            f"{target_approved_hosts}. Aborting migration to unverified host."
        )

    if url_db_name != target_expected_db:
        raise ValueError(
            f"Pre-migration check failed: Target database name in URL is '{url_db_name}', "
            f"which does not match expected production database '{target_expected_db}'."
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

    actual_db = live_meta.get("database", "").strip().lower()
    actual_user = live_meta.get("user", "").strip()
    server_ip = (live_meta.get("server_ip") or "").strip().lower()

    # Reject forbidden non-production keywords in live catalog
    for kw in FORBIDDEN_PROD_KEYWORDS:
        if kw in actual_db:
            raise ValueError(
                f"SAFETY VIOLATION: Live database name '{actual_db}' contains non-production keyword '{kw}'."
            )
        if kw in actual_user.lower():
            raise ValueError(
                f"SAFETY VIOLATION: Live connected user '{actual_user}' contains non-production keyword '{kw}'."
            )

    if actual_db != target_expected_db:
        raise ValueError(
            f"Pre-migration check failed: Connected catalog is '{actual_db}', "
            f"expected '{target_expected_db}'."
        )

    if target_expected_user and actual_user != target_expected_user:
        raise ValueError(
            f"Pre-migration check failed: Connected user role is '{actual_user}', "
            f"expected privileged production migrator role '{target_expected_user}'."
        )

    server_ip_clean = server_ip.split("/")[0] if server_ip else ""
    host_resolved_ip = ""
    if target_host in target_approved_hosts:
        try:
            host_resolved_ip = socket.gethostbyname(target_host)
        except Exception:
            pass

    ip_matches = (
        (server_ip and server_ip in target_approved_hosts)
        or (server_ip_clean and server_ip_clean in target_approved_hosts)
        or (host_resolved_ip and (server_ip == host_resolved_ip or server_ip_clean == host_resolved_ip))
    )

    if server_ip and server_ip != target_host and not ip_matches:
        raise ValueError(
            f"Pre-migration check failed: Connected server network address '{server_ip}' "
            f"is not in approved production hosts list {target_approved_hosts}."
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
    """CLI Entrypoint for production pre-migration guard."""
    try:
        result = run_production_target_verification()
        print("==============================================================================")
        print("PRODUCTION MIGRATION TARGET VERIFICATION: PASSED")
        print(f"Target Database : {result['database']}")
        print(f"Connected User  : {result['user']}")
        print(f"Host / Server   : {result['host']} ({result.get('server_ip')})")
        print(f"Sanitized DSN   : {result['sanitized_url']}")
        print("==============================================================================")
        sys.exit(0)
    except Exception as exc:
        print("==============================================================================", file=sys.stderr)
        print("PRODUCTION MIGRATION TARGET VERIFICATION: FAILED", file=sys.stderr)
        print(f"Error: {exc}", file=sys.stderr)
        print("==============================================================================", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
