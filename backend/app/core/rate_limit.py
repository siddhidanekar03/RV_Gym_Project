import time
from collections import defaultdict, deque
from threading import Lock
from typing import Callable
from fastapi import Request, HTTPException, status


class SlidingWindowRateLimiter:
    """Thread-safe sliding window in-memory rate limiter."""

    def __init__(self):
        self._lock = Lock()
        self._requests = defaultdict(deque)

    def check_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> None:
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            queue = self._requests[key]
            # Discard timestamps outside window
            while queue and queue[0] < cutoff:
                queue.popleft()

            if len(queue) >= max_requests:
                retry_after = int(queue[0] + window_seconds - now) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please slow down and try again shortly.",
                    headers={"Retry-After": str(max(1, retry_after))},
                )

            queue.append(now)

    def reset(self) -> None:
        """Clear all rate limiting entries (for testing)."""
        with self._lock:
            self._requests.clear()


limiter = SlidingWindowRateLimiter()


def rate_limit(max_requests: int = 10, window_seconds: int = 60) -> Callable:
    """FastAPI dependency for rate limiting by client IP and path."""

    async def dependency(request: Request) -> None:
        # Determine client identifier
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown_ip"

        key = f"{client_ip}:{request.url.path}"
        limiter.check_rate_limit(key, max_requests, window_seconds)

    return dependency
