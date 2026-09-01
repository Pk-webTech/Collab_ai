from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from uuid import UUID

from ..auth import get_current_user, CurrentUser
from ..db import get_pool
from ..llm import stream_chat_completion
from ..retrieval import retrieve_context

router = APIRouter(prefix="/api/chat", tags=["chat"])

HISTORY_LIMIT = 20  # last N messages sent to the model as context


class ChatIn(BaseModel):
    conversation_id: UUID
    message: str


async def _load_conversation_owner(pool, conversation_id: UUID) -> str | None:
    return await pool.fetchval(
        "select owner_id from conversations where id = $1", conversation_id
    )


@router.post("")
async def send_message(body: ChatIn, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()

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

    # Pull recent history (including the message we just inserted) for context.
    rows = await pool.fetch(
        """
        select role, content from messages
        where conversation_id = $1
        order by created_at desc
        limit $2
        """,
        body.conversation_id,
        HISTORY_LIMIT,
    )
    history = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    context = await retrieve_context(pool, owner_id=user.id, room_id=None, query=body.message)

    async def event_stream():
        full_reply = []
        async for chunk in stream_chat_completion(history, context=context):
            full_reply.append(chunk)
            yield chunk

        # Persist the assistant's full reply once streaming finishes.
        await pool.execute(
            "insert into messages (conversation_id, role, content) values ($1, 'assistant', $2)",
            body.conversation_id,
            "".join(full_reply),
        )
        await pool.execute(
            "update conversations set updated_at = now() where id = $1",
            body.conversation_id,
        )

    return StreamingResponse(event_stream(), media_type="text/plain")
