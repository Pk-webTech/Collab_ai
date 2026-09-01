-- Phase 2 schema: group rooms, membership via join code, room messages,
-- and Supabase Realtime so the frontend can subscribe directly (no
-- backend WebSocket server needed).
-- Run this in the Supabase SQL editor AFTER db/schema.sql.

create table if not exists public.rooms (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  owner_id uuid not null references public.profiles (id) on delete cascade,
  -- Short shareable code, e.g. "7F3K9Q" -- simplest free-tier invite
  -- mechanism (no email service required). Anyone with the code can join.
  join_code text not null unique,
  created_at timestamptz not null default now()
);

create table if not exists public.room_members (
  room_id uuid not null references public.rooms (id) on delete cascade,
  user_id uuid not null references public.profiles (id) on delete cascade,
  joined_at timestamptz not null default now(),
  primary key (room_id, user_id)
);

create table if not exists public.room_messages (
  id uuid primary key default gen_random_uuid(),
  room_id uuid not null references public.rooms (id) on delete cascade,
  sender_type text not null check (sender_type in ('user', 'ai')),
  -- null when sender_type = 'ai'
  user_id uuid references public.profiles (id) on delete set null,
  content text not null,
  created_at timestamptz not null default now()
);

create index if not exists room_messages_room_id_idx on public.room_messages (room_id, created_at);

-- Auto-add the creator as a member (and owner) of their own room.
create or replace function public.handle_new_room()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.room_members (room_id, user_id) values (new.id, new.owner_id);
  return new;
end;
$$;

drop trigger if exists on_room_created on public.rooms;
create trigger on_room_created
  after insert on public.rooms
  for each row execute procedure public.handle_new_room();

-- RLS
alter table public.rooms enable row level security;
alter table public.room_members enable row level security;
alter table public.room_messages enable row level security;

create policy "rooms are readable by members" on public.rooms
  for select using (
    exists (
      select 1 from public.room_members rm
      where rm.room_id = rooms.id and rm.user_id = auth.uid()
    )
  );

create policy "any signed-in user can create a room" on public.rooms
  for insert with check (auth.uid() = owner_id);

create policy "members list is readable by members" on public.room_members
  for select using (
    exists (
      select 1 from public.room_members rm
      where rm.room_id = room_members.room_id and rm.user_id = auth.uid()
    )
  );

create policy "room messages are readable by members" on public.room_messages
  for select using (
    exists (
      select 1 from public.room_members rm
      where rm.room_id = room_messages.room_id and rm.user_id = auth.uid()
    )
  );

-- Note: inserts to rooms/room_members/room_messages happen through the
-- FastAPI backend (postgres role, bypasses RLS) so it can validate join
-- codes and trigger AI replies. RLS above governs the frontend's direct
-- Supabase Realtime subscriptions (select-only).

-- Enable Realtime replication for room_messages so the frontend can
-- subscribe to inserts without any backend WebSocket code.
alter publication supabase_realtime add table public.room_messages;
