"""
Thin Redis caching layer, meant to point at a free Upstash Redis database
(or any standard Redis instance). Entirely optional: if REDIS_URL isn't set,
every call here becomes a no-op and the app behaves exactly as it did
without caching -- so this is safe to leave unset in local dev.
"""
import os
import json
import hashlib
from typing import Optional

_client = None
_checked_env = False


def _get_client():
    global _client, _checked_env
    if _checked_env:
        return _client
    _checked_env = True

    url = os.environ.get("REDIS_URL")
    if not url:
        return None

    import redis.asyncio as redis  # imported lazily; only needed if configured

    _client = redis.from_url(url, decode_responses=True)
    return _client


async def close():
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def make_key(*parts: str) -> str:
    raw = ":".join(parts)
    return "cache:" + hashlib.sha256(raw.encode()).hexdigest()


async def get_json(key: str) -> Optional[dict]:
    client = _get_client()
    if client is None:
        return None
    try:
        raw = await client.get(key)
    except Exception:
        # Redis being unreachable should never break the app -- just skip the cache.
        return None
    return json.loads(raw) if raw else None


async def set_json(key: str, value: dict, ttl_seconds: int = 300) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        await client.set(key, json.dumps(value), ex=ttl_seconds)
    except Exception:
        pass