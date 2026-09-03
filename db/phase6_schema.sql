-- Phase 6 schema: personal long-term memory.
-- Run this in the Supabase SQL editor AFTER schema.sql through phase5_schema.sql.

create table if not exists public.user_memories (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.profiles (id) on delete cascade,
  content text not null,
  created_at timestamptz not null default now()
);

create index if not exists user_memories_owner_id_idx on public.user_memories (owner_id, created_at desc);

alter table public.user_memories enable row level security;

create policy "memories are owner-only" on public.user_memories
  for all using (owner_id = auth.uid()) with check (owner_id = auth.uid());

-- Note: inserts (including the automatic background extraction) happen
-- through the FastAPI backend (postgres role, bypasses RLS), which scopes
-- everything to the verified JWT's user id before writing. RLS above is a
-- second line of defense for any direct frontend reads.