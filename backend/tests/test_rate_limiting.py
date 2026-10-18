import time
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException, Request, status
import fakeredis

from backend.app.core.config import (
    Settings,
    sanitize_redis_url,
    validate_production_security,
    validate_redis_url,
)
from backend.app.core.rate_limit import (
    BaseRateLimiter,
    InMemoryRateLimiter,
    RedisRateLimiter,
    RateLimiterProxy,
    create_rate_limiter,
    _sanitize_url,
    limiter,
    rate_limit,
)
from backend.app.core.auth import get_client_ip


def test_in_memory_rate_limiter_thresholds():
    """Verify in-memory sliding window enforces threshold and returns Retry-After header."""
    rl = InMemoryRateLimiter()
    key = "192.168.1.1:/api/v1/test"

    for _ in range(5):
        rl.check_rate_limit(key, max_requests=5, window_seconds=60)

    with pytest.raises(HTTPException) as exc_info:
        rl.check_rate_limit(key, max_requests=5, window_seconds=60)

    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "Retry-After" in exc_info.value.headers
    retry_after = int(exc_info.value.headers["Retry-After"])
    assert 1 <= retry_after <= 60

    rl.reset()
    # After reset, request should succeed
    rl.check_rate_limit(key, max_requests=5, window_seconds=60)


def test_in_memory_sliding_window_expiration():
    """Verify expired timestamps outside the sliding window are pruned."""
    rl = InMemoryRateLimiter()
    key = "192.168.1.2:/api/v1/test"

    # Add 2 requests at t = 1000 and t = 1005 with window = 10
    with patch("time.time", side_effect=[1000.0, 1005.0, 1006.0, 1011.0]):
        rl.check_rate_limit(key, max_requests=2, window_seconds=10)
        rl.check_rate_limit(key, max_requests=2, window_seconds=10)

        # 3rd request at t = 1006 should be blocked
        with pytest.raises(HTTPException) as exc_info:
            rl.check_rate_limit(key, max_requests=2, window_seconds=10)
        assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS

        # 4th request at t = 1011: t = 1000 has expired (cutoff 1001), 1 active slot remains -> passes
        rl.check_rate_limit(key, max_requests=2, window_seconds=10)


def test_backend_selection_by_environment():
    """Verify create_rate_limiter selects appropriate backend based on configuration."""
    # Explicit memory backend
    mem_cfg = MagicMock()
    mem_cfg.RATE_LIMITER_BACKEND = "memory"
    mem_cfg.ENVIRONMENT = "test"
    mem_cfg.REDIS_URL = None
    lim = create_rate_limiter(mem_cfg)
    assert lim.backend_name == "memory"
    assert isinstance(lim, InMemoryRateLimiter)

    # Auto backend with no Redis URL -> memory
    auto_no_url = MagicMock()
    auto_no_url.RATE_LIMITER_BACKEND = "auto"
    auto_no_url.ENVIRONMENT = "development"
    auto_no_url.REDIS_URL = None
    lim2 = create_rate_limiter(auto_no_url)
    assert lim2.backend_name == "memory"

    # Auto backend with unreachable Redis URL in development -> falls back to memory
    auto_bad_url = MagicMock()
    auto_bad_url.RATE_LIMITER_BACKEND = "auto"
    auto_bad_url.ENVIRONMENT = "development"
    auto_bad_url.REDIS_URL = "redis://127.0.0.1:65500/0"
    auto_bad_url.REDIS_CONNECT_TIMEOUT = 0.1
    auto_bad_url.REDIS_SOCKET_TIMEOUT = 0.1
    lim3 = create_rate_limiter(auto_bad_url)
    assert lim3.backend_name == "memory"


def test_staging_rejects_memory_backend_with_one_and_multiple_workers(tmp_path):
    """Verify staging unconditionally rejects memory backend for both 1 and multiple workers."""
    secret_key = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    qr_key = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
    ext_uploads = (tmp_path / "uploads").as_posix()

    # Staging with 1 worker and memory limiter must be rejected
    staging_cfg_1w = Settings(
        ENVIRONMENT="staging",
        DATABASE_URL="postgresql+psycopg2://rvf_app:testPass123@staging-db:5432/rvfitness_staging?sslmode=disable",
        SECRET_KEY=secret_key,
        QR_SIGNING_KEY=qr_key,
        UPLOADS_DIR=ext_uploads,
        RATE_LIMITER_BACKEND="memory",
        WORKERS_COUNT=1,
    )
    with pytest.raises(ValueError) as exc1:
        validate_production_security(staging_cfg_1w)
    assert "in-memory rate limiting is strictly forbidden" in str(exc1.value)

    # Staging with 4 workers and memory limiter must also be rejected
    staging_cfg_4w = Settings(
        ENVIRONMENT="staging",
        DATABASE_URL="postgresql+psycopg2://rvf_app:testPass123@staging-db:5432/rvfitness_staging?sslmode=disable",
        SECRET_KEY=secret_key,
        QR_SIGNING_KEY=qr_key,
        UPLOADS_DIR=ext_uploads,
        RATE_LIMITER_BACKEND="memory",
        WORKERS_COUNT=4,
    )
    with pytest.raises(ValueError) as exc4:
        validate_production_security(staging_cfg_4w)
    assert "in-memory rate limiting is strictly forbidden" in str(exc4.value)


def test_production_rejects_memory_backend_with_one_and_multiple_workers(tmp_path):
    """Verify production unconditionally rejects memory backend for both 1 and multiple workers."""
    secret_key = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    qr_key = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
    ext_uploads = (tmp_path / "uploads").as_posix()

    # Production with 1 worker and memory limiter must be rejected
    prod_cfg_1w = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql+psycopg2://rvf_app:testPass123@db.internal:5432/rvfitness?sslmode=require",
        SECRET_KEY=secret_key,
        QR_SIGNING_KEY=qr_key,
        UPLOADS_DIR=ext_uploads,
        RATE_LIMITER_BACKEND="memory",
        WORKERS_COUNT=1,
    )
    with pytest.raises(ValueError) as exc1:
        validate_production_security(prod_cfg_1w)
    assert "in-memory rate limiting is strictly forbidden" in str(exc1.value)

    # Production with 4 workers and memory limiter must also be rejected
    prod_cfg_4w = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql+psycopg2://rvf_app:testPass123@db.internal:5432/rvfitness?sslmode=require",
        SECRET_KEY=secret_key,
        QR_SIGNING_KEY=qr_key,
        UPLOADS_DIR=ext_uploads,
        RATE_LIMITER_BACKEND="memory",
        WORKERS_COUNT=4,
    )
    with pytest.raises(ValueError) as exc4:
        validate_production_security(prod_cfg_4w)
    assert "in-memory rate limiting is strictly forbidden" in str(exc4.value)


def test_staging_and_production_reject_missing_and_malformed_redis_urls(tmp_path):
    """Verify staging and production fail closed when REDIS_URL is missing, empty, or malformed."""
    secret_key = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    qr_key = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
    ext_uploads = (tmp_path / "uploads").as_posix()

    # Staging with redis backend but empty REDIS_URL
    staging_empty_url = Settings(
        ENVIRONMENT="staging",
        DATABASE_URL="postgresql+psycopg2://rvf_app:testPass123@staging-db:5432/rvfitness_staging?sslmode=disable",
        SECRET_KEY=secret_key,
        QR_SIGNING_KEY=qr_key,
        UPLOADS_DIR=ext_uploads,
        RATE_LIMITER_BACKEND="redis",
        REDIS_URL="",
    )
    with pytest.raises(ValueError) as exc1:
        validate_production_security(staging_empty_url)
    assert "REDIS_URL must be configured" in str(exc1.value)

    # Staging with auto backend but missing REDIS_URL
    staging_auto_no_url = Settings(
        ENVIRONMENT="staging",
        DATABASE_URL="postgresql+psycopg2://rvf_app:testPass123@staging-db:5432/rvfitness_staging?sslmode=disable",
        SECRET_KEY=secret_key,
        QR_SIGNING_KEY=qr_key,
        UPLOADS_DIR=ext_uploads,
        RATE_LIMITER_BACKEND="auto",
        REDIS_URL=None,
    )
    with pytest.raises(ValueError) as exc2:
        validate_production_security(staging_auto_no_url)
    assert "REDIS_URL must be configured" in str(exc2.value)

    # Production with malformed scheme and password
    prod_malformed_url = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql+psycopg2://rvf_app:testPass123@db.internal:5432/rvfitness?sslmode=require",
        SECRET_KEY=secret_key,
        QR_SIGNING_KEY=qr_key,
        UPLOADS_DIR=ext_uploads,
        RATE_LIMITER_BACKEND="redis",
        REDIS_URL="http://admin:LeakedPassword999@redis.internal:6379",
    )
    with pytest.raises(ValueError) as exc3:
        validate_production_security(prod_malformed_url)
    assert "REDIS_URL must start with redis:// or rediss://" in str(exc3.value)
    # Ensure raw password is NOT revealed in the validation error message
    assert "LeakedPassword999" not in str(exc3.value)
    assert "***" in str(exc3.value)


def test_create_rate_limiter_enforces_redis_in_staging_and_production():
    """Verify create_rate_limiter factory rejects memory limiter in staging and production."""
    # Staging with memory backend
    staging_cfg = MagicMock()
    staging_cfg.ENVIRONMENT = "staging"
    staging_cfg.RATE_LIMITER_BACKEND = "memory"
    staging_cfg.REDIS_URL = None
    with pytest.raises(ValueError) as exc_staging:
        create_rate_limiter(staging_cfg)
    assert "in-memory rate limiting is strictly forbidden" in str(exc_staging.value)

    # Production with memory backend
    prod_cfg = MagicMock()
    prod_cfg.ENVIRONMENT = "production"
    prod_cfg.RATE_LIMITER_BACKEND = "memory"
    prod_cfg.REDIS_URL = None
    with pytest.raises(ValueError) as exc_prod:
        create_rate_limiter(prod_cfg)
    assert "in-memory rate limiting is strictly forbidden" in str(exc_prod.value)

    # Staging with auto backend but no Redis URL
    staging_auto = MagicMock()
    staging_auto.ENVIRONMENT = "staging"
    staging_auto.RATE_LIMITER_BACKEND = "auto"
    staging_auto.REDIS_URL = None
    with pytest.raises(ValueError) as exc_auto:
        create_rate_limiter(staging_auto)
    assert "REDIS_URL must be configured" in str(exc_auto.value)


def test_credential_masking_in_redis_url():
    """Verify Redis URLs with passwords have credentials redacted in logs and errors."""
    raw_url = "redis://rvf_admin:SuperSecretPass123!@cache.internal:6379/1"
    sanitized = _sanitize_url(raw_url)
    assert "SuperSecretPass123!" not in sanitized
    assert sanitized == "redis://rvf_admin:***@cache.internal:6379/1"

    cfg = Settings(REDIS_URL=raw_url)
    assert cfg.get_sanitized_redis_url() == "redis://rvf_admin:***@cache.internal:6379/1"


def test_redis_rate_limiter_lua_atomic_sliding_window():
    """Verify RedisRateLimiter uses atomic Lua script and enforces bounded TTL."""
    fake_client = fakeredis.FakeRedis()
    rl = RedisRateLimiter(
        redis_url="redis://localhost:6379/0",
        environment="test",
        redis_client=fake_client,
    )
    assert rl.backend_name == "redis"
    assert rl.is_healthy() is True

    key = "user_101:/api/v1/resource"

    for _ in range(5):
        rl.check_rate_limit(key, max_requests=5, window_seconds=60)

    # 6th request blocked
    with pytest.raises(HTTPException) as exc_info:
        rl.check_rate_limit(key, max_requests=5, window_seconds=60)

    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "Retry-After" in exc_info.value.headers
    retry_after = int(exc_info.value.headers["Retry-After"])
    assert 1 <= retry_after <= 60

    # Verify key TTL is bounded (window 60 + 2 buffer)
    namespaced_key = f"rvf:rl:test:{key}"
    ttl = fake_client.ttl(namespaced_key)
    assert 55 <= ttl <= 62

    # Reset cleans up
    rl.reset()
    assert fake_client.exists(namespaced_key) == 0


def test_redis_rate_limiter_multi_instance_concurrency():
    """Verify multiple worker instances share identical sliding window state in Redis."""
    fake_shared_server = fakeredis.FakeServer()
    worker_1_client = fakeredis.FakeRedis(server=fake_shared_server)
    worker_2_client = fakeredis.FakeRedis(server=fake_shared_server)

    limiter_worker_1 = RedisRateLimiter(
        redis_url="redis://localhost:6379/0",
        environment="staging",
        redis_client=worker_1_client,
    )
    limiter_worker_2 = RedisRateLimiter(
        redis_url="redis://localhost:6379/0",
        environment="staging",
        redis_client=worker_2_client,
    )

    key = "10.0.0.5:/api/v1/auth/login"

    # Worker 1 receives 3 requests
    for _ in range(3):
        limiter_worker_1.check_rate_limit(key, max_requests=5, window_seconds=60)

    # Worker 2 receives 2 requests
    for _ in range(2):
        limiter_worker_2.check_rate_limit(key, max_requests=5, window_seconds=60)

    # Total requests across cluster = 5. Next request on Worker 1 must be blocked
    with pytest.raises(HTTPException) as exc_w1:
        limiter_worker_1.check_rate_limit(key, max_requests=5, window_seconds=60)
    assert exc_w1.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    # Next request on Worker 2 must also be blocked
    with pytest.raises(HTTPException) as exc_w2:
        limiter_worker_2.check_rate_limit(key, max_requests=5, window_seconds=60)
    assert exc_w2.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_redis_rate_limiter_namespace_isolation():
    """Verify staging and production namespaces do not share or overwrite rate limits."""
    fake_server = fakeredis.FakeServer()
    client_staging = fakeredis.FakeRedis(server=fake_server)
    client_prod = fakeredis.FakeRedis(server=fake_server)

    staging_limiter = RedisRateLimiter(
        redis_url="redis://localhost:6379/0",
        environment="staging",
        redis_client=client_staging,
    )
    prod_limiter = RedisRateLimiter(
        redis_url="redis://localhost:6379/0",
        environment="production",
        redis_client=client_prod,
    )

    shared_key = "192.168.1.100:/api/v1/auth/login"

    # Exhaust staging limit (5 requests)
    for _ in range(5):
        staging_limiter.check_rate_limit(shared_key, max_requests=5, window_seconds=60)

    # 6th staging request blocked
    with pytest.raises(HTTPException) as exc_staging:
        staging_limiter.check_rate_limit(shared_key, max_requests=5, window_seconds=60)
    assert exc_staging.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    # Production limiter with same key has full capacity
    prod_limiter.check_rate_limit(shared_key, max_requests=5, window_seconds=60)

    # Staging reset leaves production keys untouched
    staging_limiter.reset()
    assert client_staging.exists(f"rvf:rl:production:{shared_key}") == 1
    assert client_staging.exists(f"rvf:rl:staging:{shared_key}") == 0


def test_redis_rate_limiter_fail_closed_in_staging_production():
    """Verify Redis connection loss raises HTTP 503 in staging/production without silent fallback."""
    faulty_client = MagicMock()
    # Mock script execution throwing Redis connection error
    faulty_client.register_script.return_value = MagicMock(side_effect=ConnectionError("Connection to Redis lost"))

    # In production, must fail closed with HTTP 503 and Retry-After header
    prod_limiter = RedisRateLimiter(
        redis_url="redis://cache.internal:6379/0",
        environment="production",
        redis_client=faulty_client,
    )
    with pytest.raises(HTTPException) as exc_prod:
        prod_limiter.check_rate_limit("1.2.3.4:/api/v1/auth/login", max_requests=5, window_seconds=60)
    assert exc_prod.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert exc_prod.value.headers.get("Retry-After") == "5"

    # In staging, must also fail closed with HTTP 503
    staging_limiter = RedisRateLimiter(
        redis_url="redis://cache.internal:6379/0",
        environment="staging",
        redis_client=faulty_client,
    )
    with pytest.raises(HTTPException) as exc_staging:
        staging_limiter.check_rate_limit("1.2.3.4:/api/v1/auth/login", max_requests=5, window_seconds=60)
    assert exc_staging.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    # In development/test, must fall back to in-memory limiter without throwing 503
    dev_limiter = RedisRateLimiter(
        redis_url="redis://localhost:6379/0",
        environment="development",
        redis_client=faulty_client,
    )
    # Should not raise 503; falls back to internal memory limiter
    dev_limiter.check_rate_limit("1.2.3.4:/api/v1/auth/login", max_requests=5, window_seconds=60)


def test_reverse_proxy_trusted_ip_resolution():
    """Verify client IP derivation honors X-Forwarded-For only when peer is in TRUSTED_PROXIES."""
    # Mock request from untrusted direct peer in production
    untrusted_req = MagicMock(spec=Request)
    untrusted_req.client = MagicMock(host="203.0.113.50")
    untrusted_req.headers = {"x-forwarded-for": "198.51.100.22"}

    with patch("backend.app.core.auth.settings.ENVIRONMENT", "production"):
        with patch("backend.app.core.auth.settings.TRUSTED_PROXIES", ["127.0.0.1", "10.0.0.1"]):
            ip = get_client_ip(untrusted_req)
            # Untrusted peer direct IP must be returned, not spoofed forwarded header
            assert ip == "203.0.113.50"

    # Mock request from trusted proxy (10.0.0.1) in production
    trusted_req = MagicMock(spec=Request)
    trusted_req.client = MagicMock(host="10.0.0.1")
    trusted_req.headers = {"x-forwarded-for": "198.51.100.22, 10.0.0.1"}

    with patch("backend.app.core.auth.settings.ENVIRONMENT", "production"):
        with patch("backend.app.core.auth.settings.TRUSTED_PROXIES", ["127.0.0.1", "10.0.0.1"]):
            ip = get_client_ip(trusted_req)
            # Trusted proxy forwards genuine client IP
            assert ip == "198.51.100.22"


def test_rate_limiter_proxy_delegation():
    """Verify RateLimiterProxy properly delegates and allows backend switching."""
    mem_limiter = InMemoryRateLimiter()
    proxy = RateLimiterProxy(mem_limiter)
    assert proxy.backend_name == "memory"
    assert proxy.is_healthy() is True

    proxy.check_rate_limit("client:path", max_requests=2, window_seconds=60)
    proxy.reset()

    # Switch target backend
    fake_client = fakeredis.FakeRedis()
    redis_limiter = RedisRateLimiter(
        redis_url="redis://localhost:6379/0",
        environment="test",
        redis_client=fake_client,
    )
    proxy.set_target(redis_limiter)
    assert proxy.backend_name == "redis"
    assert proxy.is_healthy() is True
    proxy.close()


@pytest.mark.asyncio
async def test_rate_limit_fastapi_dependency():
    """Verify rate_limit dependency resolves client IP and path, enforcing threshold."""
    limiter.reset()
    dep = rate_limit(max_requests=2, window_seconds=60)

    req = MagicMock(spec=Request)
    req.client = MagicMock(host="192.168.1.55")
    req.headers = {}
    req.url = MagicMock(path="/api/v1/auth/login")

    # First 2 requests succeed
    await dep(req)
    await dep(req)

    # 3rd request blocked
    with pytest.raises(HTTPException) as exc_info:
        await dep(req)
    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    limiter.reset()


def test_redis_url_credential_masking_variants():
    """Verify password masking protects credentials across all URL formats and error strings."""
    secret = "SuperSecretPassword123"

    # Format 1: Empty username (redis://:password@host:port/db)
    url_empty_user = f"redis://:{secret}@staging-redis:6379/0"
    masked_empty_user = sanitize_redis_url(url_empty_user)
    assert secret not in masked_empty_user
    assert "redis://:***@staging-redis:6379/0" == masked_empty_user

    # Format 2: Explicit username (redis://user:password@host:port/db)
    url_with_user = f"redis://rvf_admin:{secret}@staging-redis:6379/0"
    masked_with_user = sanitize_redis_url(url_with_user)
    assert secret not in masked_with_user
    assert "redis://rvf_admin:***@staging-redis:6379/0" == masked_with_user

    # Format 3: Rediss SSL scheme
    url_ssl = f"rediss://:{secret}@secure-redis.internal:6380/0"
    masked_ssl = sanitize_redis_url(url_ssl)
    assert secret not in masked_ssl
    assert "rediss://:***@secure-redis.internal:6380/0" == masked_ssl

    # Format 4: URL embedded inside exception or log message
    err_msg = f"Failed to connect to redis://:{secret}@redis-host:6379/0: connection refused"
    masked_err = _sanitize_url(err_msg)
    assert secret not in masked_err
    assert "redis://:***@redis-host:6379/0" in masked_err

    # Format 5: URL without credentials remains unmodified
    no_creds = "redis://staging-redis:6379/0"
    assert sanitize_redis_url(no_creds) == no_creds


def test_redis_url_validation_hostname_and_port():
    """Verify validate_redis_url validates hostname and port, redacting credentials on failure."""
    secret = "SensitiveToken888"

    # Valid URLs must pass without error
    valid_urls = [
        "redis://localhost:6379/0",
        "redis://staging-redis:6379/0",
        f"redis://:{secret}@localhost:6379/0",
        f"redis://admin:{secret}@localhost:6379/0",
        "redis://localhost/0",
        f"rediss://:{secret}@secure-host:6380/0",
    ]
    for url in valid_urls:
        validate_redis_url(url)

    # Invalid cases must be rejected and must redact credentials in exception messages
    invalid_cases = [
        # Missing hostname
        (f"redis://:{secret}@:6379/0", "hostname is required"),
        ("redis://:6379/0", "hostname is required"),
        ("redis://", "hostname is required"),
        # Invalid non-numeric port
        (f"redis://:{secret}@localhost:abc/0", "invalid port"),
        # Out-of-range port
        (f"redis://:{secret}@localhost:70000/0", "invalid port"),
        (f"redis://:{secret}@localhost:0/0", "port must be between 1 and 65535"),
        # Unsupported schemes
        (f"http://:{secret}@localhost:6379", "must start with redis:// or rediss://"),
        (f"postgres://user:{secret}@localhost:5432/db", "must start with redis:// or rediss://"),
        # Empty or whitespace
        ("", "cannot be empty"),
    ]

    for bad_url, expected_substr in invalid_cases:
        with pytest.raises(ValueError) as exc:
            validate_redis_url(bad_url)
        err = str(exc.value)
        assert expected_substr.lower() in err.lower()
        assert secret not in err
        if secret in bad_url:
            assert "***" in err


def test_redis_rate_limiter_init_rejects_malformed_url_safely():
    """Verify RedisRateLimiter validates URL before connecting, rejecting malformed URLs safely."""
    secret = "UnleakedPass777"
    malformed_url = f"redis://:{secret}@:6379/0"

    with pytest.raises(ValueError) as exc:
        RedisRateLimiter(redis_url=malformed_url, environment="test")

    err = str(exc.value)
    assert "hostname is required" in err
    assert secret not in err
    assert "***" in err


def test_staging_and_production_rejects_empty_user_malformed_url(tmp_path):
    """Verify staging and production reject empty-user malformed Redis URLs with credentials masked."""
    secret_key = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    qr_key = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
    ext_uploads = (tmp_path / "uploads").as_posix()
    secret_pass = "TopSecretRedisPassword999"

    # Missing hostname with empty user
    bad_cfg = Settings(
        ENVIRONMENT="staging",
        DATABASE_URL="postgresql+psycopg2://rvf_app:testPass123@staging-db:5432/rvfitness_staging?sslmode=disable",
        SECRET_KEY=secret_key,
        QR_SIGNING_KEY=qr_key,
        UPLOADS_DIR=ext_uploads,
        RATE_LIMITER_BACKEND="redis",
        REDIS_URL=f"redis://:{secret_pass}@:6379/0",
    )
    with pytest.raises(ValueError) as exc:
        validate_production_security(bad_cfg)

    err = str(exc.value)
    assert "hostname is required" in err
    assert secret_pass not in err
    assert "***" in err
