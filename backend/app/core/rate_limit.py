import logging
import math
import re
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from threading import Lock
from typing import Any, Callable, Dict, Optional

from fastapi import HTTPException, Request, status

from backend.app.core.config import sanitize_redis_url, settings, validate_redis_url

logger = logging.getLogger("rvfitness.rate_limit")

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None  # type: ignore
    REDIS_AVAILABLE = False


def _sanitize_url(url: Optional[str]) -> str:
    """Mask password credentials in Redis URL for safe logging and error reporting."""
    return sanitize_redis_url(url)


LUA_SLIDING_WINDOW = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_limit = tonumber(ARGV[3])
local member = ARGV[4]

local clear_before = now - window
redis.call('ZREMRANGEBYSCORE', key, '-inf', clear_before)
local current_count = redis.call('ZCARD', key)

if current_count < max_limit then
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, math.ceil(window) + 2)
    return {1, 0, current_count + 1}
else
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 1
    if oldest and #oldest >= 2 then
        retry_after = math.max(1, math.ceil(tonumber(oldest[2]) + window - now))
    end
    return {0, retry_after, current_count}
end
"""


class BaseRateLimiter(ABC):
    """Abstract interface for rate limiting backends."""

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Name of the active rate limiting backend ('memory' or 'redis')."""
        pass

    @abstractmethod
    def check_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> None:
        """
        Verify request within sliding window.
        Raises HTTP 429 when threshold exceeded.
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """Clear rate limit records for testing or maintenance."""
        pass

    @abstractmethod
    def is_healthy(self) -> bool:
        """Check if rate limiting backend is operational."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Release backend connections and resources."""
        pass


class InMemoryRateLimiter(BaseRateLimiter):
    """Thread-safe sliding window in-memory rate limiter."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._requests: Dict[str, deque] = defaultdict(deque)

    @property
    def backend_name(self) -> str:
        return "memory"

    def check_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> None:
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            queue = self._requests[key]
            while queue and queue[0] < cutoff:
                queue.popleft()

            if len(queue) >= max_requests:
                retry_after = max(1, min(window_seconds, math.ceil(queue[0] + window_seconds - now)))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please slow down and try again shortly.",
                    headers={"Retry-After": str(retry_after)},
                )

            queue.append(now)

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()

    def is_healthy(self) -> bool:
        return True

    def close(self) -> None:
        self.reset()


# Backward-compatibility alias
SlidingWindowRateLimiter = InMemoryRateLimiter


class RedisRateLimiter(BaseRateLimiter):
    """Distributed Redis-backed sliding window rate limiter with atomic Lua script."""

    def __init__(
        self,
        redis_url: str,
        environment: Optional[str] = None,
        socket_timeout: float = 2.0,
        socket_connect_timeout: float = 2.0,
        redis_client: Optional[Any] = None,
    ) -> None:
        self._raw_url = redis_url
        self._sanitized_url = _sanitize_url(redis_url)
        self._environment = (environment or getattr(settings, "ENVIRONMENT", "development")).strip().lower()
        self._prefix = f"rvf:rl:{self._environment}:"
        self._fallback_limiter = InMemoryRateLimiter()

        # Validate URL scheme, hostname, and port before attempting connection
        validate_redis_url(redis_url)

        if redis_client is not None:
            self._client = redis_client
        else:
            if not REDIS_AVAILABLE:
                raise RuntimeError(
                    f"Redis client library is not installed. Unable to connect to {self._sanitized_url}."
                )
            self._client = redis.Redis.from_url(
                redis_url,
                socket_timeout=socket_timeout,
                socket_connect_timeout=socket_connect_timeout,
                decode_responses=False,
            )

        self._lua_script = self._client.register_script(LUA_SLIDING_WINDOW)

    @property
    def backend_name(self) -> str:
        return "redis"

    @property
    def client(self) -> Any:
        return self._client

    def check_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> None:
        now = time.time()
        redis_key = f"{self._prefix}{key}"
        member = f"{now:.6f}:{uuid.uuid4().hex}"

        try:
            res = self._lua_script(
                keys=[redis_key],
                args=[now, window_seconds, max_requests, member],
            )
        except Exception as exc:
            sanitized_err = _sanitize_url(str(exc))
            if self._environment in {"staging", "production"}:
                logger.error(
                    f"CRITICAL: Distributed rate limiter failure in {self._environment} for key '{key}': {sanitized_err}"
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Rate limiting service temporarily unavailable. Please retry shortly.",
                    headers={"Retry-After": "5"},
                )
            else:
                logger.warning(
                    f"Redis rate limiter unavailable ({sanitized_err}); falling back to in-memory rate limiting."
                )
                self._fallback_limiter.check_rate_limit(key, max_requests, window_seconds)
                return

        allowed = int(res[0])
        retry_after = int(res[1])

        if allowed == 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down and try again shortly.",
                headers={"Retry-After": str(max(1, retry_after))},
            )

    def reset(self) -> None:
        """Clear rate limit keys matching this environment namespace."""
        try:
            pattern = f"{self._prefix}*"
            keys = self._client.keys(pattern)
            if keys:
                self._client.delete(*keys)
        except Exception as exc:
            sanitized_err = _sanitize_url(str(exc))
            logger.warning(f"Error resetting Redis rate limit keys: {sanitized_err}")
        self._fallback_limiter.reset()

    def is_healthy(self) -> bool:
        """Execute a quick ping to verify Redis connectivity."""
        try:
            return bool(self._client.ping())
        except Exception:
            return False

    def close(self) -> None:
        try:
            if hasattr(self._client, "close"):
                self._client.close()
        except Exception as exc:
            sanitized_err = _sanitize_url(str(exc))
            logger.warning(f"Error closing Redis client: {sanitized_err}")
        self._fallback_limiter.close()


class RateLimiterProxy(BaseRateLimiter):
    """
    Proxy rate limiter delegating to active backend implementation.
    Allows runtime switching and testing.
    """

    def __init__(self, target: BaseRateLimiter) -> None:
        self._target = target

    @property
    def target(self) -> BaseRateLimiter:
        return self._target

    def set_target(self, target: BaseRateLimiter) -> None:
        self._target = target

    @property
    def backend_name(self) -> str:
        return self._target.backend_name

    def check_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> None:
        self._target.check_rate_limit(key, max_requests, window_seconds)

    def reset(self) -> None:
        self._target.reset()

    def is_healthy(self) -> bool:
        return self._target.is_healthy()

    def close(self) -> None:
        self._target.close()


def create_rate_limiter(config: Any = None) -> BaseRateLimiter:
    """Factory creating appropriate rate limiter based on environment configuration."""
    cfg = config or settings
    backend_mode = getattr(cfg, "RATE_LIMITER_BACKEND", "auto").strip().lower()
    env = getattr(cfg, "ENVIRONMENT", "development").strip().lower()
    redis_url = getattr(cfg, "REDIS_URL", None)

    if backend_mode == "memory":
        if env in {"staging", "production"}:
            raise ValueError(
                f"CRITICAL: In {env}, in-memory rate limiting is strictly forbidden. "
                "Distributed rate limiting via Redis is required regardless of worker count. "
                "Set RATE_LIMITER_BACKEND to 'redis' (or 'auto') and configure REDIS_URL."
            )
        return InMemoryRateLimiter()

    if backend_mode == "redis" or (backend_mode == "auto" and redis_url and redis_url.strip()):
        if not redis_url or not redis_url.strip():
            if env in {"staging", "production"}:
                raise ValueError(
                    f"CRITICAL: In {env}, REDIS_URL must be configured to support distributed rate limiting."
                )
            return InMemoryRateLimiter()

        try:
            validate_redis_url(redis_url)
            limiter_instance = RedisRateLimiter(
                redis_url=redis_url.strip(),
                environment=env,
                socket_timeout=getattr(cfg, "REDIS_SOCKET_TIMEOUT", 2.0),
                socket_connect_timeout=getattr(cfg, "REDIS_CONNECT_TIMEOUT", 2.0),
            )
            # Startup ping verification
            if not limiter_instance.is_healthy():
                if env in {"staging", "production"}:
                    sanitized = _sanitize_url(redis_url)
                    raise ConnectionError(
                        f"CRITICAL: Failed to connect to Redis at {sanitized} in {env} environment."
                    )
                else:
                    logger.warning("Redis not reachable during initialization; falling back to in-memory rate limiter.")
                    return InMemoryRateLimiter()
            return limiter_instance
        except Exception as exc:
            if env in {"staging", "production"}:
                raise
            sanitized = _sanitize_url(str(exc))
            logger.warning(f"Failed to initialize Redis rate limiter ({sanitized}); using in-memory limiter.")
            return InMemoryRateLimiter()

    if env in {"staging", "production"}:
        raise ValueError(
            f"CRITICAL: In {env}, REDIS_URL must be configured to support distributed rate limiting."
        )

    return InMemoryRateLimiter()


# Global limiter singleton proxy
limiter = RateLimiterProxy(create_rate_limiter(settings))


from backend.app.core.auth import get_client_ip


def rate_limit(max_requests: int = 10, window_seconds: int = 60) -> Callable:
    """FastAPI dependency for rate limiting by client IP and request path."""

    async def dependency(request: Request) -> None:
        client_ip = get_client_ip(request) or "unknown_ip"
        key = f"{client_ip}:{request.url.path}"
        limiter.check_rate_limit(key, max_requests, window_seconds)

    return dependency
