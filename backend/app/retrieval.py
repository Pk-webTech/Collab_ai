from dataclasses import dataclass

from .embeddings import embed_query as _embed_query_sync
import asyncio

TOP_K = 5
# Chunks with a cosine distance above this are considered too weak a match
# to be worth including as context (distance 0 = identical, 2 = opposite).
MAX_DISTANCE = 0.6


@dataclass
class RetrievalResult:
    context: str | None  # formatted text to feed the model, or None
    sources: list[dict]  # structured citation data for the frontend, [] if none


async def retrieve_context(pool, *, owner_id: str, room_id: str | None, query: str) -> RetrievalResult:
    """
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

    return RetrievalResult(context=context, sources=sources)
