from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from ..auth import get_current_user, CurrentUser
from ..db import get_pool
from ..extract import extract_text, UnsupportedFileType
from ..chunking import chunk_text
from ..embeddings import embed_texts
from ..ratelimit import check_rate_limit
import asyncio
import os

router = APIRouter(prefix="/api/documents", tags=["documents"])

MAX_FILE_BYTES = 5 * 1024 * 1024  # 5MB -- generous for free-tier Postgres storage
UPLOAD_RATE_LIMIT = int(os.environ.get("UPLOAD_RATE_LIMIT_PER_MINUTE", "10"))


class DocumentOut(BaseModel):
    id: UUID
    filename: str
    char_count: int
    status: str
    created_at: str


async def _assert_room_member(pool, room_id: UUID, user_id: str):
    is_member = await pool.fetchval(
        "select 1 from room_members where room_id = $1 and user_id = $2", room_id, user_id
    )
    if not is_member:
        raise HTTPException(403, "You're not a member of this room")


async def _process_document(document_id: UUID, text: str):
    """
    Runs after the upload response has already been sent (see
    BackgroundTasks below). Chunking + embedding is the slow part of an
    upload -- doing it here means the request returns immediately with
    status 'processing', and the frontend picks up the 'ready' (or 'failed')
    transition live via the Supabase Realtime subscription on `documents`
    (see db/phase5_schema.sql).
    """
    pool = get_pool()
    try:
        chunks = chunk_text(text)
        if chunks:
            vectors = await asyncio.to_thread(embed_texts, chunks)
            rows_to_insert = [
                (document_id, i, chunk, vector) for i, (chunk, vector) in enumerate(zip(chunks, vectors))
            ]
            await pool.executemany(
                """
                insert into document_chunks (document_id, chunk_index, content, embedding)
                values ($1, $2, $3, $4)
                """,
                rows_to_insert,
            )
        await pool.execute("update documents set status = 'ready' where id = $1", document_id)
    except Exception:
        await pool.execute("update documents set status = 'failed' where id = $1", document_id)


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    room_id: UUID | None = None, user: CurrentUser = Depends(get_current_user)
):
    pool = get_pool()
    if room_id is not None:
        await _assert_room_member(pool, room_id, user.id)
        rows = await pool.fetch(
            """
            select id, filename, char_count, status, created_at
            from documents where room_id = $1
            order by created_at desc
            """,
            room_id,
        )
    else:
        rows = await pool.fetch(
            """
            select id, filename, char_count, status, created_at
            from documents where owner_id = $1 and room_id is null
            order by created_at desc
            """,
            user.id,
        )
    return [dict(r) for r in rows]


@router.post("/upload", response_model=DocumentOut)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    room_id: UUID | None = Form(default=None),
    user: CurrentUser = Depends(get_current_user),
):
    pool = get_pool()
    check_rate_limit(f"upload:{user.id}", UPLOAD_RATE_LIMIT, 60)
    if room_id is not None:
        await _assert_room_member(pool, room_id, user.id)

    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(400, "File too large (5MB limit)")

    try:
        text = extract_text(file.filename, data)
    except UnsupportedFileType as e:
        raise HTTPException(400, str(e))

    if not text.strip():
        raise HTTPException(400, "Couldn't extract any text from that file")

    doc = await pool.fetchrow(
        """
        insert into documents (owner_id, room_id, filename, char_count, status)
        values ($1, $2, $3, $4, 'processing')
        returning id, filename, char_count, status, created_at
        """,
        user.id,
        room_id,
        file.filename,
        len(text),
    )

    # Chunking + embedding happens after the response is returned -- the
    # frontend gets the 'processing' row now and the 'ready' update later
    # via Realtime, rather than the request hanging until it's all done.
    background_tasks.add_task(_process_document, doc["id"], text)

    return dict(doc)


@router.delete("/{document_id}")
async def delete_document(document_id: UUID, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    doc = await pool.fetchrow(
        "select owner_id, room_id from documents where id = $1", document_id
    )
    if doc is None:
        raise HTTPException(404, "Document not found")

    if doc["room_id"] is not None:
        await _assert_room_member(pool, doc["room_id"], user.id)
    elif str(doc["owner_id"]) != user.id:
        raise HTTPException(403, "Not your document")

    await pool.execute("delete from documents where id = $1", document_id)
    return {"deleted": True}