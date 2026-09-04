import os
import json
import asyncpg
from typing import Optional
from pgvector.asyncpg import register_vector

_pool: Optional[asyncpg.Pool] = None


async def _init_connection(conn: asyncpg.Connection):
    await register_vector(conn)
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
        format="text",
    )


async def init_pool():
    """Create the shared connection pool. Called once on app startup."""
    global _pool
    database_url = os.environ["DATABASE_URL"]
    _pool = await asyncpg.create_pool(
        dsn=database_url,
        min_size=5,          # was 1 -- opens all connections at startup instead
        max_size=5,          # of paying a TLS handshake mid-request
        statement_cache_size=0,
        init=_init_connection,
        command_timeout=30,
    )
    return _pool


async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized. Did startup run?")
    return _pool
