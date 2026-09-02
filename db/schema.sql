-- Phase 1 schema: profiles, personal conversations, messages.
-- Run this in the Supabase SQL editor (free tier project).
-- pgvector is enabled here too, ready for Phase 3 (RAG) so you don't
-- have to re-run migrations later.

create extension if not exists vector;

-- One row per auth.users, created automatically on signup.
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text,
  display_name text,
  created_at timestamptz not null default now()
);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, email, display_name)
  values (new.id, new.email, split_part(new.email, '@', 1));
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- Personal conversations (Phase 1 = personal space only; group rooms come in Phase 2).
create table if not exists public.conversations (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.profiles (id) on delete cascade,
  title text not null default 'New chat',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations (id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  created_at timestamptz not null default now()
);

create index if not exists messages_conversation_id_idx on public.messages (conversation_id, created_at);

-- Row Level Security: personal data must never be readable by another user.
alter table public.profiles enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;

create policy "profiles are self-readable" on public.profiles
  for select using (auth.uid() = id);

create policy "conversations are owner-only" on public.conversations
  for all using (auth.uid() = owner_id) with check (auth.uid() = owner_id);

create policy "messages follow parent conversation ownership" on public.messages
  for all using (
    exists (
      select 1 from public.conversations c
      where c.id = messages.conversation_id and c.owner_id = auth.uid()
    )
  ) with check (
    exists (
      select 1 from public.conversations c
      where c.id = messages.conversation_id and c.owner_id = auth.uid()
    )
  );

-- Note: the FastAPI backend connects with the postgres role (via DATABASE_URL),
-- which bypasses RLS by design -- the backend itself enforces ownership using
-- the verified Supabase JWT (see app/auth.py). RLS here is a second line of
-- defense in case anything ever queries Supabase directly (e.g. Phase 2+
-- realtime subscriptions from the frontend).