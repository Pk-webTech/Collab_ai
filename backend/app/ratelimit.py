"""
Simple in-memory sliding-window rate limiter. Good enough for a single
free-tier instance (Render's free plan runs exactly one process) -- if you
ever scale to multiple instances, swap the dict below for Redis (see
app/cache.py) without changing any call sites.

Deliberately called explicitly inside each endpoint (after you already have
the caller's verified user id from Depends(get_current_user)), rather than
as its own FastAPI dependency -- that avoids any ambiguity about dependency
execution order.
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException

_hits: dict[str, deque] = defaultdict(deque)


def check_rate_limit(key: str, limit: int, window_seconds: int) -> None:
    """Raises HTTP 429 if `key` has already made `limit` calls within the
    last `window_seconds`; otherwise records this call and returns."""
    now = time.monotonic()
    hits = _hits[key]

    while hits and now - hits[0] > window_seconds:
        hits.popleft()

    if len(hits) >= limit:
        retry_after = max(1, int(window_seconds - (now - hits[0])) + 1)
        raise HTTPException(
            status_code=429,
            detail="Too many requests -- slow down a little and try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )

    hits.append(now)