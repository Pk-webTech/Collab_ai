from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from uuid import UUID
import asyncio
import os

from ..auth import get_current_user, CurrentUser
from ..db import get_pool
from ..llm import stream_chat_completion
from ..retrieval import retrieve_context
from ..memory import extract_and_store_memory
from ..ratelimit import check_rate_limit

router = APIRouter(prefix="/api/chat", tags=["chat"])

HISTORY_LIMIT = 20  # last N messages sent to the model as context
MEMORY_LIMIT = 20  # most recent remembered facts to include in the prompt
CHAT_RATE_LIMIT = int(os.environ.get("CHAT_RATE_LIMIT_PER_MINUTE", "20"))


class ChatIn(BaseModel):
    conversation_id: UUID
    message: str


async def _load_conversation_owner(pool, conversation_id: UUID) -> str | None:
    return await pool.fetchval(
        "select owner_id from conversations where id = $1", conversation_id
    )


@router.post("")
async def send_message(
    body: ChatIn,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
):
    pool = get_pool()
    check_rate_limit(f"chat:{user.id}", CHAT_RATE_LIMIT, 60)

    owner = await _load_conversation_owner(pool, body.conversation_id)
    if owner is None:
        raise HTTPException(404, "Conversation not found")
    if str(owner) != user.id:
        raise HTTPException(403, "Not your conversation")

    # Persist the user's message immediately.
    await pool.execute(
        "insert into messages (conversation_id, role, content) values ($1, 'user', $2)",
        body.conversation_id,
        body.message,
    )

    # Pull recent history, search the user's documents, and pull remembered
    # facts about them concurrently -- three independent reads, no reason
    # to wait on one before starting the next.
    history_rows, retrieval, memory_rows = await asyncio.gather(
        pool.fetch(
            """
            select role, content from messages
            where conversation_id = $1
            order by created_at desc
            limit $2
            """,
            body.conversation_id,
            HISTORY_LIMIT,
        ),
        retrieve_context(pool, owner_id=user.id, room_id=None, query=body.message),
        pool.fetch(
            "select content from user_memories where owner_id = $1 order by created_at desc limit $2",
            user.id,
            MEMORY_LIMIT,
        ),
    )
    history = [{"role": r["role"], "content": r["content"]} for r in reversed(history_rows)]
    memories = [r["content"] for r in memory_rows]

    async def event_stream():
        full_reply = []
        async for chunk in stream_chat_completion(history, context=retrieval.context, memories=memories):
            full_reply.append(chunk)
            yield chunk

        # Persist the assistant's full reply (plus which sources backed it,
        # if any) once streaming finishes.
        await pool.execute(
            """
            insert into messages (conversation_id, role, content, sources)
            values ($1, 'assistant', $2, $3)
            """,
            body.conversation_id,
            "".join(full_reply),
            retrieval.sources or None,
        )
        await pool.execute(
            "update conversations set updated_at = now() where id = $1",
            body.conversation_id,
        )

    # Runs the memory-extraction call after the response is fully sent, so
    # it never adds latency to the reply itself.
    background_tasks.add_task(extract_and_store_memory, user.id, body.message)

    return StreamingResponse(event_stream(), media_type="text/plain", background=background_tasks)