import logging
import secrets
import string
from datetime import datetime
from uuid import UUID
import asyncio
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user, CurrentUser
from ..db import get_pool
from ..llm import stream_chat_completion
from ..retrieval import retrieve_context
from ..ratelimit import check_rate_limit

router = APIRouter(prefix="/api/rooms", tags=["rooms"])

logger = logging.getLogger("app.rooms")

AI_TRIGGER = "@ai"
HISTORY_LIMIT = 20
ROOM_MESSAGE_RATE_LIMIT = int(os.environ.get("ROOM_MESSAGE_RATE_LIMIT_PER_MINUTE", "30"))


def _generate_join_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


# All timestamp fields below MUST be `datetime`, not `str`. asyncpg returns
# timestamptz columns as datetime objects and pydantic v2 will not coerce
# datetime -> str, so `str` raised ResponseValidationError and turned every
# one of these endpoints into a 500. FastAPI serialises datetime to ISO-8601,
# which is what the frontend's `created_at: string` types already expect.
class RoomOut(BaseModel):
    id: UUID
    name: str
    owner_id: UUID
    join_code: str
    created_at: datetime


class CreateRoomIn(BaseModel):
    name: str


class RenameRoomIn(BaseModel):
    name: str


class JoinRoomIn(BaseModel):
    join_code: str


class MemberOut(BaseModel):
    user_id: UUID
    display_name: str | None
    role: str
    joined_at: datetime


class RoomMessageOut(BaseModel):
    id: UUID
    sender_type: str
    user_id: UUID | None
    display_name: str | None = None
    content: str
    created_at: datetime
    sources: list[dict] | None = None


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


async def _assert_owner(pool, room_id: UUID, user_id: str):
    owner_id = await pool.fetchval("select owner_id from rooms where id = $1", room_id)
    if owner_id is None:
        raise HTTPException(404, "Room not found")
    if str(owner_id) != user_id:
        raise HTTPException(403, "Only the room owner can do that")


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
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Room name can't be empty")

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
        name,
        user.id,
        code,
    )
    return dict(row)


@router.patch("/{room_id}", response_model=RoomOut)
async def rename_room(
    room_id: UUID, body: RenameRoomIn, user: CurrentUser = Depends(get_current_user)
):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Room name can't be empty")

    pool = get_pool()
    await _assert_owner(pool, room_id, user.id)
    row = await pool.fetchrow(
        """
        update rooms set name = $1 where id = $2
        returning id, name, owner_id, join_code, created_at
        """,
        name,
        room_id,
    )
    return dict(row)


@router.delete("/{room_id}")
async def delete_room(room_id: UUID, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    await _assert_owner(pool, room_id, user.id)
    await pool.execute("delete from rooms where id = $1", room_id)
    return {"deleted": True}


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
        insert into room_members (room_id, user_id, role)
        values ($1, $2, 'member')
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
        select rm.user_id, p.display_name, rm.role, rm.joined_at
        from room_members rm
        join profiles p on p.id = rm.user_id
        where rm.room_id = $1
        order by rm.joined_at asc
        """,
        room_id,
    )
    return [dict(r) for r in rows]


@router.delete("/{room_id}/members/{member_id}")
async def remove_or_leave(
    room_id: UUID, member_id: UUID, user: CurrentUser = Depends(get_current_user)
):
    """A member can remove themselves (leave); the owner can remove anyone
    but themselves (use delete_room to disband the room instead)."""
    pool = get_pool()
    await _assert_member(pool, room_id, user.id)

    owner_id = await pool.fetchval("select owner_id from rooms where id = $1", room_id)
    is_self = str(member_id) == user.id

    if is_self:
        # Previously the owner could leave their own room. The room then had
        # an owner_id pointing at a non-member: nobody could rename or delete
        # it, and it vanished from everyone's room list.
        if str(owner_id) == user.id:
            raise HTTPException(400, "You own this room -- delete it instead of leaving")
    else:
        await _assert_owner(pool, room_id, user.id)
        if str(owner_id) == str(member_id):
            raise HTTPException(400, "Owner can't be removed -- delete the room instead")

    await pool.execute(
        "delete from room_members where room_id = $1 and user_id = $2", room_id, member_id
    )
    return {"removed": True}


@router.get("/{room_id}/messages", response_model=list[RoomMessageOut])
async def get_room_messages(room_id: UUID, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    await _assert_member(pool, room_id, user.id)
    rows = await pool.fetch(
        """
        select m.id, m.sender_type, m.user_id, p.display_name, m.content, m.created_at, m.sources
        from room_messages m
        left join profiles p on p.id = m.user_id
        where m.room_id = $1
        order by m.created_at asc
        """,
        room_id,
    )
    return [dict(r) for r in rows]


async def _generate_ai_reply(room_id: UUID, user_id: str, prompt: str) -> None:
    """
    Runs after the POST response has been sent. The reply reaches every
    client (including the sender) over Realtime, so nothing here needs to
    be in the request body -- and keeping it out of the request means the
    sender's HTTP call doesn't hang for the 10-30s the model takes.
    Best-effort: a failure here must never surface as a failed send.
    """
    try:
        pool = get_pool()
        history_rows, retrieval = await asyncio.gather(
            pool.fetch(
                """
                select sender_type, content from room_messages
                where room_id = $1
                order by created_at desc
                limit $2
                """,
                room_id,
                HISTORY_LIMIT,
            ),
            retrieve_context(pool, owner_id=user_id, room_id=room_id, query=prompt),
        )
        history = [
            {"role": "assistant" if r["sender_type"] == "ai" else "user", "content": r["content"]}
            for r in reversed(history_rows)
        ]

        reply_parts = []
        async for chunk in stream_chat_completion(history, context=retrieval.context):
            reply_parts.append(chunk)
        ai_reply = "".join(reply_parts) or "…"

        await pool.execute(
            """
            insert into room_messages (room_id, sender_type, user_id, content, sources)
            values ($1, 'ai', null, $2, $3)
            """,
            room_id,
            ai_reply,
            retrieval.sources or None,
        )
    except Exception:
        logger.exception("ai_reply_failed room_id=%s", room_id)


@router.post("/{room_id}/messages", response_model=RoomMessageOut)
async def send_room_message(
    room_id: UUID,
    body: SendRoomMessageIn,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Inserts the message; the frontend hears about it (for every member,
    including the sender) via a Supabase Realtime subscription rather than
    this response. If the message starts with "@ai", an assistant reply is
    generated in the background and persisted, reaching the whole room the
    same way any user message does.
    """
    content = body.content.strip()
    if not content:
        raise HTTPException(400, "Message can't be empty")

    pool = get_pool()
    check_rate_limit(f"room_message:{user.id}", ROOM_MESSAGE_RATE_LIMIT, 60)
    await _assert_member(pool, room_id, user.id)

    row = await pool.fetchrow(
        """
        insert into room_messages (room_id, sender_type, user_id, content)
        values ($1, 'user', $2, $3)
        returning id, sender_type, user_id, content, created_at, sources
        """,
        room_id,
        user.id,
        content,
    )
    result = dict(row)
    display_name = await pool.fetchval("select display_name from profiles where id = $1", user.id)
    result["display_name"] = display_name

    if content.lower().startswith(AI_TRIGGER):
        background_tasks.add_task(_generate_ai_reply, room_id, user.id, content)

    return result