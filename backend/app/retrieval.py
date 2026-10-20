import asyncio
from dataclasses import dataclass
from functools import lru_cache

from .embeddings import embed_query as _embed_query_sync
from . import cache

MAX_DISTANCE = 1.0
TOP_K = 8

# How long a (scope, query) retrieval result stays cached in Redis. Short
# enough that a newly uploaded document shows up in search within a few
# minutes without needing explicit cache invalidation.
CACHE_TTL_SECONDS = 300

# In-process cache of query embeddings. Embeddings depend only on the text
# (never on who asked or which documents exist), so they can be reused
# forever and across users. Costs ~1.5 KB per entry.
EMBED_CACHE_SIZE = 1024


@dataclass
class RetrievalResult:
    context: str | None  # formatted text to feed the model, or None
    sources: list[dict]  # structured citation data for the frontend, [] if none


@lru_cache(maxsize=EMBED_CACHE_SIZE)
def _embed_cached(text: str) -> tuple[float, ...]:
    return tuple(_embed_query_sync(text))


async def _embed(text: str) -> list[float]:
    # sentence-transformers is CPU-bound and synchronous -- offload it so it
    # doesn't block the event loop for other requests. lru_cache is
    # thread-safe for this use.
    return list(await asyncio.to_thread(_embed_cached, text))


async def retrieve_context(pool, *, owner_id: str, room_id: str | None, query: str) -> RetrievalResult:
    """
    Scope: personal chat passes room_id=None (searches only that user's own
    personal documents); group room chat passes the room_id (searches that
    room's shared documents).

    Results are cached in Redis (if configured) per (scope, normalized
    query) for CACHE_TTL_SECONDS, so repeated or near-simultaneous questions
    -- common in group rooms -- skip re-searching.

    The Redis lookup and the query embedding run at the same time. On a
    cache miss (the common case in personal chat) this removes the Redis
    round trip from the critical path; on a hit the embedding is simply
    discarded (and is usually an in-process cache hit anyway).
    """
    scope = f"room:{room_id}" if room_id is not None else f"user:{owner_id}"
    # Include the ready document set so uploads/deletes invalidate old results,
    # including cached misses. Keep query case: codes and names can be case-sensitive.
    revision = await pool.fetchval(
        """select coalesce(string_agg(id::text, ',' order by id), '')
        from documents where status = 'ready' and
        (($2::uuid is null and room_id is null and owner_id = $1::uuid)
         or room_id = $2::uuid)""", owner_id, room_id,
    )
    cache_key = cache.make_key("retrieval", scope, revision, query.strip())

    cached, query_vector = await asyncio.gather(
        cache.get_json(cache_key),
        _embed(query),
    )
    if cached is not None:
        return RetrievalResult(context=cached["context"], sources=cached["sources"])

    if room_id is None:
        rows = await pool.fetch(
            """
            select dc.document_id, dc.chunk_index, dc.content, d.filename,
                   dc.embedding <=> $1 as distance
            from document_chunks dc
            join documents d on d.id = dc.document_id
            where d.room_id is null and d.owner_id = $2 and d.status = 'ready'
            order by dc.embedding <=> $1
            limit $3
            """,
            query_vector,
            owner_id,
            TOP_K,
        )
    else:
        rows = await pool.fetch(
            """
            select dc.document_id, dc.chunk_index, dc.content, d.filename,
                   dc.embedding <=> $1 as distance
            from document_chunks dc
            join documents d on d.id = dc.document_id
            where d.room_id = $2 and d.status = 'ready'
            order by dc.embedding <=> $1
            limit $3
            """,
            query_vector,
            room_id,
            TOP_K,
        )

    relevant = [r for r in rows if r["distance"] <= MAX_DISTANCE]
    if not relevant:
        await cache.set_json(cache_key, {"context": None, "sources": []}, CACHE_TTL_SECONDS)
        return RetrievalResult(context=None, sources=[])

    blocks = [f"[Source: {r['filename']}]\n{r['content']}" for r in relevant]
    context = "\n\n---\n\n".join(blocks)

    sources = [
        {
            "document_id": str(r["document_id"]),
            "filename": r["filename"],
            "chunk_index": r["chunk_index"],
            "snippet": r["content"][:280],
            "distance": round(float(r["distance"]), 4),
        }
        for r in relevant
    ]

    await cache.set_json(cache_key, {"context": context, "sources": sources}, CACHE_TTL_SECONDS)
    return RetrievalResult(context=context, sources=sources)
