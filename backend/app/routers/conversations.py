from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user, CurrentUser
from ..db import get_pool

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


# NOTE: these timestamp fields MUST be `datetime`, not `str`.
# asyncpg returns `timestamptz` columns as `datetime.datetime` objects, and
# pydantic v2 does not coerce datetime -> str. Declaring them as `str` made
# FastAPI raise ResponseValidationError and return 500 on every one of these
# endpoints. With `datetime`, FastAPI serialises them to ISO-8601 strings,
# which is exactly what the TypeScript `created_at: string` types expect.
class ConversationOut(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime
    sources: list[dict] | None = None


class CreateConversationIn(BaseModel):
    title: str | None = None


@router.get("", response_model=list[ConversationOut])
async def list_conversations(user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    rows = await pool.fetch(
        """
        select id, title, created_at, updated_at
        from conversations
        where owner_id = $1
        order by updated_at desc
        """,
        user.id,
    )
    return [dict(r) for r in rows]


@router.post("", response_model=ConversationOut)
async def create_conversation(
    body: CreateConversationIn, user: CurrentUser = Depends(get_current_user)
):
    pool = get_pool()
    row = await pool.fetchrow(
        """
        insert into conversations (owner_id, title)
        values ($1, $2)
        returning id, title, created_at, updated_at
        """,
        user.id,
        (body.title or "New chat").strip() or "New chat",
    )
    return dict(row)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def get_messages(conversation_id: UUID, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    owner = await pool.fetchval(
        "select owner_id from conversations where id = $1", conversation_id
    )
    if owner is None:
        raise HTTPException(404, "Conversation not found")
    if str(owner) != user.id:
        raise HTTPException(403, "Not your conversation")

    rows = await pool.fetch(
        """
        select id, role, content, created_at, sources
        from messages
        where conversation_id = $1
        order by created_at asc
        """,
        conversation_id,
    )
    return [dict(r) for r in rows]


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: UUID, user: CurrentUser = Depends(get_current_user)
):
    pool = get_pool()
    owner = await pool.fetchval(
        "select owner_id from conversations where id = $1", conversation_id
    )
    if owner is None:
        raise HTTPException(404, "Conversation not found")
    if str(owner) != user.id:
        raise HTTPException(403, "Not your conversation")

    await pool.execute("delete from conversations where id = $1", conversation_id)
    return {"deleted": True}