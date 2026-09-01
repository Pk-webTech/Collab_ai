import os
import asyncpg
from typing import Optional
from pgvector.asyncpg import register_vector

_pool: Optional[asyncpg.Pool] = None


async def _init_connection(conn: asyncpg.Connection):
    await register_vector(conn)


async def init_pool():
    """Create the shared connection pool. Called once on app startup."""
    global _pool
    database_url = os.environ["DATABASE_URL"]
    _pool = await asyncpg.create_pool(
        dsn=database_url,
        min_size=1,
        max_size=5,
        # Supabase's free-tier pooler is happier with statement caching off.
        statement_cache_size=0,
        init=_init_connection,
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
