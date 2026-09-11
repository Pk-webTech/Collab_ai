-- Phase 9: performance indexes.
-- Run this in the Supabase SQL editor AFTER schema.sql through phase8_fixes.sql.
-- Safe to re-run: every statement is idempotent.

-- ---------------------------------------------------------------------------
-- 1) Replace the IVFFlat vector index with HNSW.
--
-- IVFFlat picks its cluster centres when the index is built. phase3 built it
-- on an empty table, so the centres are meaningless and searches can miss
-- relevant chunks. HNSW has no training step, stays accurate as documents
-- are added, and is pgvector's recommended default.
-- ---------------------------------------------------------------------------

drop index if exists public.document_chunks_embedding_idx;

create index if not exists document_chunks_embedding_hnsw_idx
  on public.document_chunks using hnsw (embedding vector_cosine_ops);

-- ---------------------------------------------------------------------------
-- 2) Indexes for the filters retrieval applies before/after the vector
--    search (personal docs by owner, shared docs by room).
-- ---------------------------------------------------------------------------

create index if not exists documents_personal_owner_idx
  on public.documents (owner_id)
  where room_id is null;

create index if not exists documents_room_idx
  on public.documents (room_id)
  where room_id is not null;

-- ---------------------------------------------------------------------------
-- 3) Conversation list: "my conversations, newest first".
-- ---------------------------------------------------------------------------

create index if not exists conversations_owner_updated_idx
  on public.conversations (owner_id, updated_at desc);

-- ---------------------------------------------------------------------------
-- 4) Refresh planner statistics so the new indexes are used right away.
-- ---------------------------------------------------------------------------

analyze public.document_chunks;
analyze public.documents;
analyze public.conversations;

-- ---------------------------------------------------------------------------
-- 5) OPTIONAL: better filtered vector search (pgvector 0.8.0+ only).
--
-- An HNSW search returns the nearest chunks across ALL users first and the
-- owner/room filter is applied afterwards, so once many users have uploaded
-- documents, a user can get fewer than TOP_K results. Iterative scans fix
-- that by continuing the search until enough rows pass the filter.
--
-- Check your version first:
--   select extversion from pg_extension where extname = 'vector';
-- If it's 0.8.0 or higher, uncomment the line below and run it:
--
-- alter role postgres set hnsw.iterative_scan = 'relaxed_order';
-- ---------------------------------------------------------------------------