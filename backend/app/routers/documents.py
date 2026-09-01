from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from ..auth import get_current_user, CurrentUser
from ..db import get_pool
from ..extract import extract_text, UnsupportedFileType
from ..chunking import chunk_text
from ..embeddings import embed_texts
import asyncio

router = APIRouter(prefix="/api/documents", tags=["documents"])

MAX_FILE_BYTES = 5 * 1024 * 1024  # 5MB -- generous for free-tier Postgres storage


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
    file: UploadFile = File(...),
    room_id: UUID | None = Form(default=None),
    user: CurrentUser = Depends(get_current_user),
):
    pool = get_pool()
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

    chunks = chunk_text(text)
    if chunks:
        vectors = await asyncio.to_thread(embed_texts, chunks)
        rows_to_insert = [
            (doc["id"], i, chunk, vector) for i, (chunk, vector) in enumerate(zip(chunks, vectors))
        ]
        await pool.executemany(
            """
            insert into document_chunks (document_id, chunk_index, content, embedding)
            values ($1, $2, $3, $4)
            """,
            rows_to_insert,
        )

    await pool.execute("update documents set status = 'ready' where id = $1", doc["id"])

    return {**dict(doc), "status": "ready"}


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
