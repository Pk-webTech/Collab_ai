"""Smoke-test the installed runtime, model, and vector database without writes.

Unlike check_services.py, this loads/downloads the embedding model and makes
one short Groq completion request using synthetic text.
"""
import asyncio
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name('.env'))


async def main():
    from app.db import init_pool, close_pool
    from app.embeddings import embed_query
    from app.llm import stream_chat_completion
    from app.retrieval import retrieve_context
    from app import cache

    vector = await asyncio.to_thread(embed_query, 'Runtime verification sentence.')
    assert len(vector) == 384
    print('Embedding model: loaded; 384-dimensional vector generated', flush=True)
    pool = await init_pool()
    try:
        async with pool.acquire() as conn:
            distance = await conn.fetchval('select $1::vector <=> $1::vector', vector)
            assert abs(distance) < 0.001
        print('Database vector codec and cosine search: passed', flush=True)
        result = await retrieve_context(pool, owner_id=str(uuid4()), room_id=None,
                                        query='Runtime verification sentence.')
        assert result.context is None and not result.sources
        print('Retrieval for empty personal scope: passed', flush=True)
        chunks = [part async for part in stream_chat_completion(
            [{'role': 'user', 'content': 'Reply with just the word OK.'}], use_tools=False)]
        assert ''.join(chunks).strip()
        print('Live Groq streaming completion: passed', flush=True)
    finally:
        await cache.close()
        await close_pool()


if __name__ == '__main__':
    asyncio.run(main())
