-- Phase 3 schema: uploaded documents, their chunks + embeddings for RAG.
-- Run this in the Supabase SQL editor AFTER db/schema.sql and db/phase2_schema.sql.
-- Embeddings are computed locally in the backend (sentence-transformers,
-- all-MiniLM-L6-v2, 384 dims) -- no embedding API key needed, fully free.

create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.profiles (id) on delete cascade,
  -- null = personal document (only the owner can retrieve it in chat).
  -- set = shared with everyone in that room.
  room_id uuid references public.rooms (id) on delete cascade,
  filename text not null,
  char_count int not null default 0,
  status text not null default 'ready' check (status in ('processing', 'ready', 'failed')),
  created_at timestamptz not null default now()
);

create table if not exists public.document_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents (id) on delete cascade,
  chunk_index int not null,
  content text not null,
  embedding vector(384) not null,
  created_at timestamptz not null default now()
);

create index if not exists document_chunks_document_id_idx on public.document_chunks (document_id);

-- Approximate nearest-neighbour index for cosine similarity search.
-- Fine to create even with little data in it yet.
create index if not exists document_chunks_embedding_idx
  on public.document_chunks using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);

alter table public.documents enable row level security;
alter table public.document_chunks enable row level security;

create policy "personal documents are owner-readable" on public.documents
  for select using (
    (room_id is null and owner_id = auth.uid())
    or (room_id is not null and exists (
      select 1 from public.room_members rm
      where rm.room_id = documents.room_id and rm.user_id = auth.uid()
    ))
  );

create policy "chunks follow parent document visibility" on public.document_chunks
  for select using (
    exists (
      select 1 from public.documents d
      where d.id = document_chunks.document_id
      and (
        (d.room_id is null and d.owner_id = auth.uid())
        or (d.room_id is not null and exists (
          select 1 from public.room_members rm
          where rm.room_id = d.room_id and rm.user_id = auth.uid()
        ))
      )
    )
  );

-- Note: inserts/deletes happen through the FastAPI backend (postgres role,
-- bypasses RLS), which validates ownership/membership using the verified
-- Supabase JWT before writing. RLS above governs any direct frontend reads.
