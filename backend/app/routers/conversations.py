from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from uuid import UUID

from ..auth import get_current_user, CurrentUser
from ..db import get_pool

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ConversationOut(BaseModel):
    id: UUID
    title: str
    created_at: str
    updated_at: str


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: str


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
        body.title or "New chat",
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
        select id, role, content, created_at
        from messages
        where conversation_id = $1
        order by created_at asc
        """,
        conversation_id,
    )
    return [dict(r) for r in rows]
