import logging
import os
import sys
import time
from typing import Any

from fastapi import HTTPException

# Ensure backend is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.core.rate_limit import (
    RedisRateLimiter,
    create_rate_limiter,
    _sanitize_url,
)
from backend.app.core.config import Settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("verify_real_redis")

DISPOSABLE_REDIS_URL = "redis://127.0.0.1:16379/0"


def test_real_redis_lua_and_ttl():
    logger.info("Test 1: Testing Lua script sliding window and TTL against real Redis...")
    rl = RedisRateLimiter(redis_url=DISPOSABLE_REDIS_URL, environment="staging")
    assert rl.is_healthy(), "Disposable Redis should be healthy"
    key = "client_101:/api/v1/auth/login"

    # Reset any existing test keys
    rl.reset()

    # 5 requests should pass
    for i in range(5):
        rl.check_rate_limit(key, max_requests=5, window_seconds=60)
        logger.info(f"Request {i+1}/5 allowed")

    # 6th request must be blocked
    try:
        rl.check_rate_limit(key, max_requests=5, window_seconds=60)
        raise AssertionError("Expected HTTP 429 was not raised")
    except HTTPException as exc:
        assert exc.status_code == 429, f"Expected 429, got {exc.status_code}"
        assert "Retry-After" in exc.headers, "Expected Retry-After header"
        retry_after = int(exc.headers["Retry-After"])
        assert 1 <= retry_after <= 60, f"Retry-After out of bounds: {retry_after}"
        logger.info(f"Request 6 blocked as expected: HTTP 429, Retry-After: {retry_after}")

    # Check key TTL in real Redis
    raw_redis = rl.client
    namespaced_key = f"rvf:rl:staging:{key}"
    ttl = raw_redis.ttl(namespaced_key)
    logger.info(f"Real Redis key '{namespaced_key}' TTL: {ttl}s (expected ~62s)")
    assert 55 <= ttl <= 62, f"TTL out of expected range: {ttl}"

    rl.reset()
    assert raw_redis.exists(namespaced_key) == 0, "Key should be deleted after reset"
    logger.info("Test 1 PASSED.\n")


def test_real_redis_multi_instance_concurrency():
    logger.info("Test 2: Testing shared rate limit across independent limiter instances...")
    instance_1 = RedisRateLimiter(redis_url=DISPOSABLE_REDIS_URL, environment="staging")
    instance_2 = RedisRateLimiter(redis_url=DISPOSABLE_REDIS_URL, environment="staging")
    key = "client_cluster_test:/api/v1/resource"

    instance_1.reset()

    # Instance 1 sends 3 requests
    for i in range(3):
        instance_1.check_rate_limit(key, max_requests=5, window_seconds=60)
        logger.info(f"Instance 1 sent request {i+1}")

    # Instance 2 sends 2 requests
    for i in range(2):
        instance_2.check_rate_limit(key, max_requests=5, window_seconds=60)
        logger.info(f"Instance 2 sent request {i+1}")

    # Total requests = 5. Both instances should now block
    try:
        instance_1.check_rate_limit(key, max_requests=5, window_seconds=60)
        raise AssertionError("Instance 1 should have blocked 6th cluster request")
    except HTTPException as exc1:
        assert exc1.status_code == 429
        logger.info("Instance 1 correctly blocked request 6")

    try:
        instance_2.check_rate_limit(key, max_requests=5, window_seconds=60)
        raise AssertionError("Instance 2 should have blocked 6th cluster request")
    except HTTPException as exc2:
        assert exc2.status_code == 429
        logger.info("Instance 2 correctly blocked request 6")

    instance_1.reset()
    logger.info("Test 2 PASSED.\n")


def test_real_redis_window_recovery():
    logger.info("Test 3: Testing limits recover after window expiration...")
    rl = RedisRateLimiter(redis_url=DISPOSABLE_REDIS_URL, environment="staging")
    key = "client_expiry_test:/api/v1/ping"
    rl.reset()

    # Limit of 2 requests in 2 seconds
    rl.check_rate_limit(key, max_requests=2, window_seconds=2)
    rl.check_rate_limit(key, max_requests=2, window_seconds=2)

    try:
        rl.check_rate_limit(key, max_requests=2, window_seconds=2)
        raise AssertionError("Expected 3rd immediate request to be blocked")
    except HTTPException as exc:
        assert exc.status_code == 429
        logger.info("Rate limit exceeded as expected")

    # Wait for window expiration
    logger.info("Sleeping 2.2 seconds for window to slide...")
    time.sleep(2.2)

    # Now request should be allowed again
    rl.check_rate_limit(key, max_requests=2, window_seconds=2)
    logger.info("Request allowed after window slide!")
    rl.reset()
    logger.info("Test 3 PASSED.\n")


def test_real_redis_namespace_isolation():
    logger.info("Test 4: Testing namespace and environment isolation on real Redis...")
    staging_limiter = RedisRateLimiter(redis_url=DISPOSABLE_REDIS_URL, environment="staging")
    prod_limiter = RedisRateLimiter(redis_url=DISPOSABLE_REDIS_URL, environment="production")
    key = "shared_ip_diff_env:/api/v1/auth/login"

    staging_limiter.reset()
    prod_limiter.reset()

    # Exhaust staging limit
    for _ in range(5):
        staging_limiter.check_rate_limit(key, max_requests=5, window_seconds=60)

    # Staging blocked
    try:
        staging_limiter.check_rate_limit(key, max_requests=5, window_seconds=60)
        raise AssertionError("Staging should be blocked")
    except HTTPException as exc:
        assert exc.status_code == 429

    # Production limiter with same client key should have full capacity
    prod_limiter.check_rate_limit(key, max_requests=5, window_seconds=60)
    logger.info("Production limiter unaffected by exhausted staging limit")

    # Staging reset should only delete staging keys
    staging_limiter.reset()
    raw = prod_limiter.client
    assert raw.exists(f"rvf:rl:production:{key}") == 1, "Production key should still exist"
    assert raw.exists(f"rvf:rl:staging:{key}") == 0, "Staging key should be deleted"
    prod_limiter.reset()
    logger.info("Test 4 PASSED.\n")


def test_real_redis_connection_loss_policy():
    logger.info("Test 5: Testing Redis connection failure policy (fail-closed in staging/prod, fallback in dev)...")
    # Unreachable port
    bad_url = "redis://127.0.0.1:16399/0"

    # In production: must fail closed with HTTP 503
    prod_rl = RedisRateLimiter(redis_url=bad_url, environment="production", socket_timeout=0.2, socket_connect_timeout=0.2)
    try:
        prod_rl.check_rate_limit("user:key", max_requests=5, window_seconds=60)
        raise AssertionError("Production should have raised HTTP 503 on Redis failure")
    except HTTPException as exc:
        assert exc.status_code == 503, f"Expected 503, got {exc.status_code}"
        assert exc.headers.get("Retry-After") == "5"
        logger.info("Production fail-closed verified: HTTP 503 with Retry-After: 5")

    # In staging: must also fail closed with HTTP 503
    staging_rl = RedisRateLimiter(redis_url=bad_url, environment="staging", socket_timeout=0.2, socket_connect_timeout=0.2)
    try:
        staging_rl.check_rate_limit("user:key", max_requests=5, window_seconds=60)
        raise AssertionError("Staging should have raised HTTP 503 on Redis failure")
    except HTTPException as exc:
        assert exc.status_code == 503, f"Expected 503, got {exc.status_code}"
        logger.info("Staging fail-closed verified: HTTP 503 with Retry-After: 5")

    # In development: must fall back to in-memory rate limiter
    dev_rl = RedisRateLimiter(redis_url=bad_url, environment="development", socket_timeout=0.2, socket_connect_timeout=0.2)
    # Should not raise HTTP 503; falls back to in-memory
    dev_rl.check_rate_limit("user:key", max_requests=5, window_seconds=60)
    logger.info("Development fallback verified: fell back to in-memory limiter without exception")
    logger.info("Test 5 PASSED.\n")


def test_real_redis_startup_failure_policy():
    logger.info("Test 6: Testing startup verification fails in staging/production if Redis unreachable...")
    bad_url = "redis://127.0.0.1:16399/0"

    staging_cfg = Settings(
        ENVIRONMENT="staging",
        DATABASE_URL="postgresql+psycopg2://rvf_app:mockPass123@staging-db:5432/rvfitness_staging?sslmode=disable",
        SECRET_KEY="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        QR_SIGNING_KEY="fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",
        RATE_LIMITER_BACKEND="redis",
        REDIS_URL=bad_url,
        REDIS_CONNECT_TIMEOUT=0.2,
        REDIS_SOCKET_TIMEOUT=0.2,
    )
    try:
        create_rate_limiter(staging_cfg)
        raise AssertionError("Startup should have failed when Redis is unreachable in staging")
    except (ConnectionError, RuntimeError) as exc:
        logger.info(f"Startup correctly failed fast in staging: {exc}")

    # In development, startup should gracefully fall back to in-memory
    dev_cfg = Settings(
        ENVIRONMENT="development",
        RATE_LIMITER_BACKEND="redis",
        REDIS_URL=bad_url,
        REDIS_CONNECT_TIMEOUT=0.2,
        REDIS_SOCKET_TIMEOUT=0.2,
    )
    limiter = create_rate_limiter(dev_cfg)
    assert limiter.backend_name == "memory", f"Expected memory fallback, got {limiter.backend_name}"
    logger.info("Startup in development gracefully fell back to in-memory rate limiter")
    logger.info("Test 6 PASSED.\n")


def test_credential_sanitization():
    logger.info("Test 7: Testing credential redaction in Redis URLs...")
    sensitive_url = "redis://rvf_user:SuperSecretPassword123!@127.0.0.1:16379/0"
    sanitized = _sanitize_url(sensitive_url)
    assert "SuperSecretPassword123!" not in sanitized
    assert sanitized == "redis://rvf_user:***@127.0.0.1:16379/0"
    logger.info(f"Sanitized URL verified: {sanitized}")

    cfg = Settings(REDIS_URL=sensitive_url)
    assert cfg.get_sanitized_redis_url() == "redis://rvf_user:***@127.0.0.1:16379/0"
    logger.info("Settings.get_sanitized_redis_url() verified")
    logger.info("Test 7 PASSED.\n")


def main():
    logger.info("Starting Real Redis Integration Verification Suite...\n")
    test_real_redis_lua_and_ttl()
    test_real_redis_multi_instance_concurrency()
    test_real_redis_window_recovery()
    test_real_redis_namespace_isolation()
    test_real_redis_connection_loss_policy()
    test_real_redis_startup_failure_policy()
    test_credential_sanitization()
    logger.info("ALL 7 REAL REDIS INTEGRATION TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
