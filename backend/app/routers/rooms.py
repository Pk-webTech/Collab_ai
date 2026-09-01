import secrets
import string
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user, CurrentUser
from ..db import get_pool
from ..llm import stream_chat_completion

router = APIRouter(prefix="/api/rooms", tags=["rooms"])

AI_TRIGGER = "@ai"
HISTORY_LIMIT = 20


def _generate_join_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


class RoomOut(BaseModel):
    id: UUID
    name: str
    owner_id: UUID
    join_code: str
    created_at: str


class CreateRoomIn(BaseModel):
    name: str


class JoinRoomIn(BaseModel):
    join_code: str


class MemberOut(BaseModel):
    user_id: UUID
    display_name: str | None
    joined_at: str


class RoomMessageOut(BaseModel):
    id: UUID
    sender_type: str
    user_id: UUID | None
    display_name: str | None = None
    content: str
    created_at: str


class SendRoomMessageIn(BaseModel):
    content: str


async def _assert_member(pool, room_id: UUID, user_id: str):
    is_member = await pool.fetchval(
        "select 1 from room_members where room_id = $1 and user_id = $2",
        room_id,
        user_id,
    )
    if not is_member:
        raise HTTPException(403, "You're not a member of this room")


@router.get("", response_model=list[RoomOut])
async def list_my_rooms(user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    rows = await pool.fetch(
        """
        select r.id, r.name, r.owner_id, r.join_code, r.created_at
        from rooms r
        join room_members rm on rm.room_id = r.id
        where rm.user_id = $1
        order by r.created_at desc
        """,
        user.id,
    )
    return [dict(r) for r in rows]


@router.post("", response_model=RoomOut)
async def create_room(body: CreateRoomIn, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    for _ in range(5):
        code = _generate_join_code()
        exists = await pool.fetchval("select 1 from rooms where join_code = $1", code)
        if not exists:
            break
    else:
        raise HTTPException(500, "Could not generate a unique join code, try again")

    row = await pool.fetchrow(
        """
        insert into rooms (name, owner_id, join_code)
        values ($1, $2, $3)
        returning id, name, owner_id, join_code, created_at
        """,
        body.name,
        user.id,
        code,
    )
    return dict(row)


@router.post("/join", response_model=RoomOut)
async def join_room(body: JoinRoomIn, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    room = await pool.fetchrow(
        "select id, name, owner_id, join_code, created_at from rooms where join_code = $1",
        body.join_code.strip().upper(),
    )
    if room is None:
        raise HTTPException(404, "No room with that code")

    await pool.execute(
        """
        insert into room_members (room_id, user_id)
        values ($1, $2)
        on conflict (room_id, user_id) do nothing
        """,
        room["id"],
        user.id,
    )
    return dict(room)


@router.get("/{room_id}/members", response_model=list[MemberOut])
async def list_members(room_id: UUID, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    await _assert_member(pool, room_id, user.id)
    rows = await pool.fetch(
        """
        select rm.user_id, p.display_name, rm.joined_at
        from room_members rm
        join profiles p on p.id = rm.user_id
        where rm.room_id = $1
        order by rm.joined_at asc
        """,
        room_id,
    )
    return [dict(r) for r in rows]


@router.get("/{room_id}/messages", response_model=list[RoomMessageOut])
async def get_room_messages(room_id: UUID, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    await _assert_member(pool, room_id, user.id)
    rows = await pool.fetch(
        """
        select m.id, m.sender_type, m.user_id, p.display_name, m.content, m.created_at
        from room_messages m
        left join profiles p on p.id = m.user_id
        where m.room_id = $1
        order by m.created_at asc
        """,
        room_id,
    )
    return [dict(r) for r in rows]


@router.post("/{room_id}/messages", response_model=RoomMessageOut)
async def send_room_message(
    room_id: UUID, body: SendRoomMessageIn, user: CurrentUser = Depends(get_current_user)
):
    """
    Inserts the message; the frontend hears about it (for every member,
    including the sender) via a Supabase Realtime subscription rather than
    this response. If the message starts with "@ai", also generates and
    persists an AI reply so it shows up for the whole room in real time.
    """
    pool = get_pool()
    await _assert_member(pool, room_id, user.id)

    row = await pool.fetchrow(
        """
        insert into room_messages (room_id, sender_type, user_id, content)
        values ($1, 'user', $2, $3)
        returning id, sender_type, user_id, content, created_at
        """,
        room_id,
        user.id,
        body.content,
    )
    result = dict(row)
    display_name = await pool.fetchval("select display_name from profiles where id = $1", user.id)
    result["display_name"] = display_name

    if body.content.strip().lower().startswith(AI_TRIGGER):
        history_rows = await pool.fetch(
            """
            select sender_type, content from room_messages
            where room_id = $1
            order by created_at desc
            limit $2
            """,
            room_id,
            HISTORY_LIMIT,
        )
        history = [
            {"role": "assistant" if r["sender_type"] == "ai" else "user", "content": r["content"]}
            for r in reversed(history_rows)
        ]

        reply_parts = []
        async for chunk in stream_chat_completion(history):
            reply_parts.append(chunk)
        ai_reply = "".join(reply_parts) or "…"

        await pool.execute(
            """
            insert into room_messages (room_id, sender_type, user_id, content)
            values ($1, 'ai', null, $2)
            """,
            room_id,
            ai_reply,
        )
        # AI message delivery to all clients happens via Realtime, same as
        # any user message -- nothing further to do here.

    return result
