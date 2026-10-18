"""
Fail-Closed PostgreSQL Integration Test Safety Guard.

Guarantees that destructive schema operations (DROP SCHEMA, CASCADE, migrations,
table truncations) can only execute against an authenticated, explicitly approved,
disposable test database instance.

Enforces:
1. Explicit opt-in environment variable: ALLOW_DESTRUCTIVE_POSTGRES_TESTS=true
2. Explicit POSTGRESQL_TEST_URL without implicit fallbacks
3. Rejection of production, staging, and live environments
4. Verification of database host against approved disposable test hosts
5. Verification of database name (_test suffix and absence of protected keywords)
6. Dedicated test role validation if configured
7. Verification of live connected database catalog and identity before destructive SQL
8. Password masking in all logs, diagnostics, and error messages
"""
import os
import sys
from typing import Dict, Any, Optional, List, Union, Callable
from urllib.parse import urlparse
import sqlalchemy as sa


DEFAULT_APPROVED_TEST_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "postgres-test",
    "test-db",
    "rvfitness-integration-db",
}

DEFAULT_APPROVED_TEST_PORTS = {5432, 15432, 5433}

FORBIDDEN_KEYWORDS = ["prod", "production", "staging", "live"]
FORBIDDEN_SYSTEM_DATABASES = {"postgres", "template0", "template1"}


def sanitize_db_url(url: Optional[str]) -> str:
    """Mask credentials in database URL to prevent credential leakage in test output."""
    if not url or not url.strip():
        return "<empty>"
    try:
        parsed = urlparse(url.strip())
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


def get_approved_test_hosts(approved_hosts: Optional[List[str]] = None) -> set:
    """Resolve the set of approved disposable test hosts."""
    if approved_hosts is not None:
        return {h.strip().lower() for h in approved_hosts if h.strip()}

    env_hosts = os.environ.get("APPROVED_POSTGRES_TEST_HOSTS", "").strip()
    if env_hosts:
        return {h.strip().lower() for h in env_hosts.split(",") if h.strip()}

    return set(DEFAULT_APPROVED_TEST_HOSTS)


def get_approved_test_ports(approved_ports: Optional[List[int]] = None) -> set:
    """Resolve the set of approved disposable test ports."""
    if approved_ports is not None:
        valid_ports = set()
        for p in approved_ports:
            if not isinstance(p, int) or not (1 <= p <= 65535):
                raise ValueError(
                    f"FATAL: Invalid approved port '{p}'. Must be integer between 1 and 65535."
                )
            valid_ports.add(p)
        return valid_ports

    env_ports = os.environ.get("APPROVED_POSTGRES_TEST_PORTS", "").strip()
    if env_ports:
        valid_ports = set()
        for item in env_ports.split(","):
            raw_p = item.strip()
            if not raw_p:
                continue
            try:
                p_val = int(raw_p)
                if not (1 <= p_val <= 65535):
                    raise ValueError(f"Port '{p_val}' out of valid range (1-65535)")
                valid_ports.add(p_val)
            except ValueError as exc:
                raise ValueError(
                    f"FATAL: APPROVED_POSTGRES_TEST_PORTS contains invalid port '{raw_p}': {exc}"
                )
        if not valid_ports:
            raise ValueError("FATAL: APPROVED_POSTGRES_TEST_PORTS is set but contains no valid ports.")
        return valid_ports

    return set(DEFAULT_APPROVED_TEST_PORTS)


def validate_disposable_test_target(
    url: Optional[str],
    approved_hosts: Optional[List[str]] = None,
    approved_ports: Optional[List[int]] = None,
    opt_in_env_var: str = "ALLOW_DESTRUCTIVE_POSTGRES_TESTS",
) -> Dict[str, Any]:
    """
    Fail closed unless target is an authenticated, approved disposable test database
    and explicit opt-in is confirmed via environment variable.

    Strictly forbids destructive schema operations against development, staging, or production.
    Raises ValueError or RuntimeError on any safety violation.
    """
    # 1. Explicit opt-in verification
    opt_in_val = os.environ.get(opt_in_env_var, "").strip().lower()
    if opt_in_val != "true":
        raise RuntimeError(
            f"FATAL: Destructive PostgreSQL tests require explicit opt-in. "
            f"Set {opt_in_env_var}=true to permit destructive schema operations (DROP SCHEMA, migrations)."
        )

    # 2. Explicit URL requirement (no silent defaults)
    if not url or not url.strip():
        raise ValueError(
            "POSTGRESQL_TEST_URL is unset or empty. "
            "Explicit configuration of an isolated disposable test database is required."
        )

    # 3. Environment check
    env = os.environ.get("ENVIRONMENT", "").strip().lower()
    if env in {"production", "staging", "prod", "live"}:
        raise RuntimeError(
            f"FATAL: Destructive PostgreSQL integration suite cannot run when ENVIRONMENT={env}."
        )

    # 4. Scheme validation
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("postgresql", "postgresql+psycopg2", "postgres"):
        raise ValueError(
            f"FATAL: Target database scheme '{parsed.scheme}' is unsupported. "
            "Only PostgreSQL disposable test databases are permitted."
        )

    # 5. Approved test host validation
    hostname = (parsed.hostname or "").strip().lower()
    allowed_hosts = get_approved_test_hosts(approved_hosts)
    if not hostname or hostname not in allowed_hosts:
        raise RuntimeError(
            f"FATAL: Host '{hostname}' is not an approved disposable test host. "
            f"Approved hosts: {sorted(list(allowed_hosts))}. "
            f"Target: {sanitize_db_url(url)}"
        )

    # 5b. Approved test port validation
    try:
        port = parsed.port if parsed.port is not None else 5432
    except ValueError as exc:
        raise ValueError(
            f"FATAL: Database URL contains malformed port: {exc}. Target: {sanitize_db_url(url)}"
        )

    if not (1 <= port <= 65535):
        raise ValueError(
            f"FATAL: Database port '{port}' is out of valid range (1-65535). Target: {sanitize_db_url(url)}"
        )

    allowed_ports = get_approved_test_ports(approved_ports)
    if port not in allowed_ports:
        raise RuntimeError(
            f"FATAL: Port '{port}' is not an approved disposable test port. "
            f"Approved ports: {sorted(list(allowed_ports))}. Target: {sanitize_db_url(url)}"
        )

    # 6. Database name validation
    db_name = (parsed.path or "").lstrip("/")
    if not db_name:
        raise ValueError(
            f"FATAL: Target database name in POSTGRESQL_TEST_URL is empty. "
            f"Target: {sanitize_db_url(url)}"
        )

    db_lower = db_name.lower()
    if any(kw in db_lower for kw in FORBIDDEN_KEYWORDS):
        raise RuntimeError(
            f"FATAL: Database name '{db_name}' contains protected keyword. Destructive tests aborted."
        )

    if db_lower in FORBIDDEN_SYSTEM_DATABASES:
        raise RuntimeError(
            f"FATAL: Database name '{db_name}' is a system database. Destructive tests aborted."
        )

    if not (db_lower.endswith("_test") or db_lower.endswith("_integration_test") or db_lower == "rvfitness_test"):
        raise RuntimeError(
            f"FATAL: Refusing to execute destructive schema operations on database '{db_name}'. "
            "Target database name must explicitly end with '_test' (e.g. rvfitness_test) "
            "to guarantee disposable test isolation."
        )

    # 7. Dedicated test role validation (if configured)
    expected_user = os.environ.get("EXPECTED_POSTGRES_TEST_USER", "").strip()
    if expected_user and parsed.username and parsed.username != expected_user:
        raise RuntimeError(
            f"FATAL: Database user '{parsed.username}' does not match expected integration test role '{expected_user}'."
        )

    return {
        "status": "preflight_ok",
        "sanitized_url": sanitize_db_url(url),
        "host": hostname,
        "port": port,
        "database": db_name,
        "user": parsed.username,
    }


def verify_live_database_identity(
    target: Union[sa.engine.Connection, sa.engine.Engine, Callable[[], Dict[str, Any]]],
    expected_db: str,
    expected_user: Optional[str] = None,
    approved_hosts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Execute live identity queries against active connection before executing destructive SQL.
    Validates current_database(), current_user, and server address.
    """
    if callable(target):
        live_meta = target()
    else:
        # target is an engine or connection
        if isinstance(target, sa.engine.Engine):
            with target.connect() as conn:
                row = conn.execute(
                    sa.text("SELECT current_database(), current_user, inet_server_addr()::text;")
                ).fetchone()
        else:
            row = target.execute(
                sa.text("SELECT current_database(), current_user, inet_server_addr()::text;")
            ).fetchone()
        live_meta = {
            "database": str(row[0]) if row and row[0] else "",
            "user": str(row[1]) if row and row[1] else "",
            "server_ip": str(row[2]) if row and row[2] else "",
        }

    actual_db = live_meta.get("database", "").strip()
    actual_user = live_meta.get("user", "").strip()
    server_ip = (live_meta.get("server_ip") or "").strip().lower()

    if actual_db != expected_db:
        raise RuntimeError(
            f"FATAL: Live connected database '{actual_db}' does not match expected test database '{expected_db}'. "
            "Aborting destructive operations."
        )

    actual_lower = actual_db.lower()
    if any(kw in actual_lower for kw in FORBIDDEN_KEYWORDS):
        raise RuntimeError(
            f"FATAL: Connected database catalog '{actual_db}' contains protected keyword."
        )

    if actual_lower in FORBIDDEN_SYSTEM_DATABASES:
        raise RuntimeError(
            f"FATAL: Connected database catalog '{actual_db}' is a system database."
        )

    if not (actual_lower.endswith("_test") or actual_lower.endswith("_integration_test") or actual_lower == "rvfitness_test"):
        raise RuntimeError(
            f"FATAL: Connected database catalog '{actual_db}' does not end with '_test'."
        )

    target_expected_user = expected_user or os.environ.get("EXPECTED_POSTGRES_TEST_USER", "").strip()
    if target_expected_user and actual_user != target_expected_user:
        raise RuntimeError(
            f"FATAL: Connected database user '{actual_user}' does not match expected integration test role '{target_expected_user}'."
        )

    allowed_hosts = get_approved_test_hosts(approved_hosts)
    clean_ip = server_ip.split("/")[0].strip()
    if clean_ip and clean_ip not in allowed_hosts:
        is_safe_local = clean_ip.startswith("127.") or clean_ip in ("::1", "localhost")
        if not is_safe_local:
            try:
                import ipaddress
                addr = ipaddress.ip_address(clean_ip)
                # Allow loopback and Docker bridge networks (172.16.0.0/12)
                is_safe_local = addr.is_loopback or (addr.is_private and clean_ip.startswith("172."))
            except ValueError:
                is_safe_local = False
        if not is_safe_local:
            raise RuntimeError(
                f"FATAL: Connected server IP address '{server_ip}' is not an approved test host: {sorted(list(allowed_hosts))}."
            )

    return {
        "status": "verified",
        "database": actual_db,
        "user": actual_user,
        "server_ip": server_ip,
    }
