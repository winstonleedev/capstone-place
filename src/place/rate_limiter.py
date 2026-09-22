import asyncio
import time
from collections import defaultdict, deque
from typing import NamedTuple
from starlette.requests import Request


class RateLimitStatus(NamedTuple):
    allowed: bool
    remaining: int
    retry_after: float  # seconds until next pixel placement allowed (0 if not limited)
    reset_in: float     # seconds until full reset or next token restore


def extract_client_ip(request: Request) -> str:
    """Extract client IP address from request headers or connection info."""
    # Check X-Forwarded-For header
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first (original client) IP in the chain
        parts = [p.strip() for p in forwarded_for.split(",") if p.strip()]
        if parts:
            return parts[0]

    # Check X-Real-IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip and real_ip.strip():
        return real_ip.strip()

    # Fallback to connection client host
    if request.client and request.client.host:
        return request.client.host

    return "127.0.0.1"


class SlidingWindowRateLimiter:
    """Per-IP sliding window rate limiter allowing N events per window seconds."""

    def __init__(self, max_requests: int = 10, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()
        self._last_cleanup = time.monotonic()

    def _cleanup_stale(self, now: float) -> None:
        """Periodically remove IPs that have had no activity for over a window."""
        if now - self._last_cleanup < 300.0:  # every 5 minutes
            return
        self._last_cleanup = now
        stale_cutoff = now - self.window_seconds
        stale_ips = [
            ip for ip, queue in self._history.items()
            if not queue or queue[-1] < stale_cutoff
        ]
        for ip in stale_ips:
            del self._history[ip]

    def _prune(self, queue: deque[float], now: float) -> None:
        cutoff = now - self.window_seconds
        while queue and queue[0] <= cutoff:
            queue.popleft()

    async def get_status(self, ip: str) -> RateLimitStatus:
        """Inspect current rate limit status without consuming a token."""
        async with self._lock:
            now = time.monotonic()
            queue = self._history[ip]
            self._prune(queue, now)

            if len(queue) >= self.max_requests:
                earliest = queue[0]
                retry_after = max(0.0, (earliest + self.window_seconds) - now)
                return RateLimitStatus(
                    allowed=False,
                    remaining=0,
                    retry_after=round(retry_after, 2),
                    reset_in=round(retry_after, 2),
                )
            else:
                remaining = self.max_requests - len(queue)
                reset_in = 0.0
                if queue:
                    reset_in = max(0.0, (queue[0] + self.window_seconds) - now)
                return RateLimitStatus(
                    allowed=True,
                    remaining=remaining,
                    retry_after=0.0,
                    reset_in=round(reset_in, 2),
                )

    async def check_and_consume(self, ip: str) -> RateLimitStatus:
        """Atomically check quota and consume one token if allowed."""
        async with self._lock:
            now = time.monotonic()
            self._cleanup_stale(now)
            queue = self._history[ip]
            self._prune(queue, now)

            if len(queue) >= self.max_requests:
                earliest = queue[0]
                retry_after = max(0.0, (earliest + self.window_seconds) - now)
                return RateLimitStatus(
                    allowed=False,
                    remaining=0,
                    retry_after=round(retry_after, 2),
                    reset_in=round(retry_after, 2),
                )

            # Consume token
            queue.append(now)
            remaining = self.max_requests - len(queue)
            reset_in = max(0.0, (queue[0] + self.window_seconds) - now)

            return RateLimitStatus(
                allowed=True,
                remaining=remaining,
                retry_after=0.0,
                reset_in=round(reset_in, 2),
            )

