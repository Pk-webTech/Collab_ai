from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
import json
from uuid import UUID
import asyncio
import logging
import os
import time
import uuid

from ..auth import get_current_user, CurrentUser
from ..db import get_pool
from ..llm import stream_chat_completion
from ..retrieval import retrieve_context
from ..memory import extract_and_store_memory
from ..ratelimit import check_rate_limit

router = APIRouter(prefix="/api/chat", tags=["chat"])

logger = logging.getLogger("app.chat")

HISTORY_LIMIT = 20  # last N messages sent to the model as context (incl. the new one)
MEMORY_LIMIT = 20  # most recent remembered facts to include in the prompt
CHAT_RATE_LIMIT = int(os.environ.get("CHAT_RATE_LIMIT_PER_MINUTE", "20"))


class ChatIn(BaseModel):
    conversation_id: UUID
    message: str = Field(min_length=1, max_length=20000)

    @field_validator("message")
    @classmethod
    def nonempty_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message can't be empty")
        return value.strip()


@router.post("")
async def send_message(
    body: ChatIn,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
):
    pool = get_pool()
    check_rate_limit(f"chat:{user.id}", CHAT_RATE_LIMIT, 60)

    t0 = time.monotonic()

    # The new message's id is generated here rather than by Postgres, so the
    # history query below can exclude it by id. That lets the insert and the
    # history read run at the same time without racing each other.
    message_id = uuid.uuid4()

    # Ownership check + insert in ONE statement: the row is only inserted if
    # the conversation belongs to this user. No row back = not found / not
    # yours (both return 404, which also avoids revealing that someone
    # else's conversation id exists).
    insert_user_message = pool.fetchval(
        """
        insert into messages (id, conversation_id, role, content)
        select $1::uuid, c.id, 'user', $3::text
        from conversations c
        where c.id = $2::uuid and c.owner_id = $4::uuid
        returning id
        """,
        message_id,
        body.conversation_id,
        body.message,
        user.id,
    )

    # Everything the model needs, fetched concurrently with the insert.
    # Previously: owner check -> insert -> (these three), i.e. 3 sequential
    # round trips before any work on the answer started. Now it's 1.
    inserted, history_rows, retrieval, memory_rows = await asyncio.gather(
        insert_user_message,
        pool.fetch(
            """
            select role, content from messages
            where conversation_id = $1 and id <> $2
            order by created_at desc
            limit $3
            """,
            body.conversation_id,
            message_id,
            HISTORY_LIMIT - 1,
        ),
        retrieve_context(pool, owner_id=user.id, room_id=None, query=body.message),
        pool.fetch(
            "select content from user_memories where owner_id = $1 order by created_at desc limit $2",
            user.id,
            MEMORY_LIMIT,
        ),
    )

    # Nothing read above has been used yet, so bailing out here never leaks
    # another user's history.
    if inserted is None:
        raise HTTPException(404, "Conversation not found")

    history = [{"role": r["role"], "content": r["content"]} for r in reversed(history_rows)]
    history.append({"role": "user", "content": body.message})
    memories = [r["content"] for r in memory_rows]

    prep_ms = (time.monotonic() - t0) * 1000

    async def event_stream():
        full_reply: list[str] = []
        first_token_ms: float | None = None
        try:
            async for chunk in stream_chat_completion(
                history, context=retrieval.context, memories=memories
            ):
                if first_token_ms is None:
                    first_token_ms = (time.monotonic() - t0) * 1000
                full_reply.append(chunk)
                yield json.dumps({"type": "delta", "text": chunk}) + "\n"
        except Exception:
            logger.exception("stream_failed conversation_id=%s", body.conversation_id)
            # The 200 header is already sent, so this is the only way to tell
            # the user anything. Without it the socket just closes.
            yield json.dumps({"type": "error", "message": "The assistant failed to respond. Please try again."}) + "\n"
            return
        finally:
            # The request-logging middleware only measures time until the
            # response headers go out, so it can't see streaming time. These
            # are the numbers that reflect what the user actually feels.
            logger.info(
                "chat_timing conversation_id=%s prep_ms=%.1f first_token_ms=%s total_ms=%.1f "
                "has_context=%s reply_chars=%d",
                body.conversation_id,
                prep_ms,
                f"{first_token_ms:.1f}" if first_token_ms is not None else "none",
                (time.monotonic() - t0) * 1000,
                retrieval.context is not None,
                sum(len(c) for c in full_reply),
            )

        if not full_reply:
            yield json.dumps({"type": "error", "message": "The assistant returned an empty reply. Please try again."}) + "\n"
            return

        # Save the reply and bump the conversation's updated_at in ONE round
        # trip (a data-modifying CTE always runs, even when not referenced).
        try:
            await pool.execute(
                """
                with saved as (
                    insert into messages (conversation_id, role, content, sources)
                    values ($1, 'assistant', $2, $3)
                )
                update conversations set updated_at = now() where id = $1
                """,
                body.conversation_id,
                "".join(full_reply),
                retrieval.sources or None,
            )
        except Exception:
            logger.exception("save_reply_failed conversation_id=%s", body.conversation_id)
            yield json.dumps({"type": "error", "message": "The reply could not be saved. Please reload the conversation."}) + "\n"
            return
        yield json.dumps({"type": "done"}) + "\n"

    # Runs the memory-extraction call after the response is fully sent, so
    # it never adds latency to the reply itself.
    background_tasks.add_task(extract_and_store_memory, user.id, body.message)

    return StreamingResponse(event_stream(), media_type="application/x-ndjson", background=background_tasks)
