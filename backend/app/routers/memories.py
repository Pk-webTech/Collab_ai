from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user, CurrentUser
from ..db import get_pool

router = APIRouter(prefix="/api/memories", tags=["memories"])


class MemoryOut(BaseModel):
    id: UUID
    content: str
    created_at: str


class CreateMemoryIn(BaseModel):
    content: str


class UpdateMemoryIn(BaseModel):
    content: str


@router.get("", response_model=list[MemoryOut])
async def list_memories(user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    rows = await pool.fetch(
        "select id, content, created_at from user_memories where owner_id = $1 order by created_at desc",
        user.id,
    )
    return [dict(r) for r in rows]


@router.post("", response_model=MemoryOut)
async def create_memory(body: CreateMemoryIn, user: CurrentUser = Depends(get_current_user)):
    content = body.content.strip()
    if not content:
        raise HTTPException(400, "Memory can't be empty")
    pool = get_pool()
    row = await pool.fetchrow(
        "insert into user_memories (owner_id, content) values ($1, $2) returning id, content, created_at",
        user.id,
        content,
    )
    return dict(row)


async def _assert_own_memory(pool, memory_id: UUID, user_id: str):
    owner = await pool.fetchval("select owner_id from user_memories where id = $1", memory_id)
    if owner is None:
        raise HTTPException(404, "Memory not found")
    if str(owner) != user_id:
        raise HTTPException(403, "Not your memory")


@router.patch("/{memory_id}", response_model=MemoryOut)
async def update_memory(
    memory_id: UUID, body: UpdateMemoryIn, user: CurrentUser = Depends(get_current_user)
):
    content = body.content.strip()
    if not content:
        raise HTTPException(400, "Memory can't be empty")
    pool = get_pool()
    await _assert_own_memory(pool, memory_id, user.id)
    row = await pool.fetchrow(
        "update user_memories set content = $1 where id = $2 returning id, content, created_at",
        content,
        memory_id,
    )
    return dict(row)


@router.delete("/{memory_id}")
async def delete_memory(memory_id: UUID, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    await _assert_own_memory(pool, memory_id, user.id)
    await pool.execute("delete from user_memories where id = $1", memory_id)
    return {"deleted": True}
