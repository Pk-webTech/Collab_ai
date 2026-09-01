from .embeddings import embed_query as _embed_query_sync
import asyncio

TOP_K = 5
# Chunks with a cosine distance above this are considered too weak a match
# to be worth including as context (distance 0 = identical, 2 = opposite).
MAX_DISTANCE = 0.6


async def retrieve_context(pool, *, owner_id: str, room_id: str | None, query: str) -> str | None:
    """
    Returns a formatted context block of the most relevant document chunks,
    or None if there are no documents in scope / nothing relevant enough.

    Scope: personal chat passes room_id=None (searches only that user's own
    personal documents); group room chat passes the room_id (searches that
    room's shared documents).
    """
    # sentence-transformers is CPU-bound and synchronous -- offload it so it
    # doesn't block the event loop for other requests.
    query_vector = await asyncio.to_thread(_embed_query_sync, query)

    if room_id is None:
        rows = await pool.fetch(
            """
            select dc.content, d.filename,
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
            select dc.content, d.filename,
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
        return None

    blocks = [f"[Source: {r['filename']}]\n{r['content']}" for r in relevant]
    return "\n\n---\n\n".join(blocks)
