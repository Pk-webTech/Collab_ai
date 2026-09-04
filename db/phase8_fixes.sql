-- Phase 8: bug fixes for the RLS policies added in phase2/phase3/phase4.
-- Run this in the Supabase SQL editor AFTER all the earlier phase scripts.
-- Safe to run more than once.

-- ---------------------------------------------------------------------------
-- 1) Fix "infinite recursion detected in policy for relation room_members"
--
-- phase2_schema.sql defines a SELECT policy ON public.room_members whose USING
-- clause itself does `select 1 from public.room_members ...`. Postgres has to
-- evaluate the policy to run that subquery, which re-enters the same policy,
-- and the query aborts with error 42P17. Every policy that transitively reads
-- room_members (including the one on public.rooms) fails with it, which breaks
-- the frontend's direct Supabase reads and its Realtime subscriptions.
--
-- The standard fix is a SECURITY DEFINER helper: it runs as its owner, so RLS
-- is not re-applied inside it and the recursion is broken.
-- ---------------------------------------------------------------------------

create or replace function public.is_room_member(p_room_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.room_members rm
    where rm.room_id = p_room_id and rm.user_id = auth.uid()
  );
$$;

revoke all on function public.is_room_member(uuid) from public;
grant execute on function public.is_room_member(uuid) to authenticated;

drop policy if exists "members list is readable by members" on public.room_members;
create policy "members list is readable by members" on public.room_members
  for select using (public.is_room_member(room_members.room_id));

drop policy if exists "rooms are readable by members" on public.rooms;
create policy "rooms are readable by members" on public.rooms
  for select using (public.is_room_member(rooms.id));

drop policy if exists "room messages are readable by members" on public.room_messages;
create policy "room messages are readable by members" on public.room_messages
  for select using (public.is_room_member(room_messages.room_id));

drop policy if exists "personal documents are owner-readable" on public.documents;
create policy "personal documents are owner-readable" on public.documents
  for select using (
    (room_id is null and owner_id = auth.uid())
    or (room_id is not null and public.is_room_member(room_id))
  );

drop policy if exists "chunks follow parent document visibility" on public.document_chunks;
create policy "chunks follow parent document visibility" on public.document_chunks
  for select using (
    exists (
      select 1 from public.documents d
      where d.id = document_chunks.document_id
      and (
        (d.room_id is null and d.owner_id = auth.uid())
        or (d.room_id is not null and public.is_room_member(d.room_id))
      )
    )
  );

-- ---------------------------------------------------------------------------
-- 2) Make the remaining policies re-runnable.
--
-- The earlier scripts use bare `create policy`, so re-running any of them
-- fails with "policy ... already exists" -- which is what makes a partially
-- applied migration so painful to recover from. Recreate them idempotently.
-- ---------------------------------------------------------------------------

drop policy if exists "any signed-in user can create a room" on public.rooms;
create policy "any signed-in user can create a room" on public.rooms
  for insert with check (auth.uid() = owner_id);

drop policy if exists "owner can update room" on public.rooms;
create policy "owner can update room" on public.rooms
  for update using (owner_id = auth.uid());

drop policy if exists "owner can delete room" on public.rooms;
create policy "owner can delete room" on public.rooms
  for delete using (owner_id = auth.uid());

drop policy if exists "leave room or be removed by owner" on public.room_members;
create policy "leave room or be removed by owner" on public.room_members
  for delete using (
    user_id = auth.uid()
    or exists (
      select 1 from public.rooms r
      where r.id = room_members.room_id and r.owner_id = auth.uid()
    )
  );

-- ---------------------------------------------------------------------------
-- 3) Realtime DELETE payloads.
--
-- By default Postgres only puts the primary key in the "old" record of a
-- DELETE, so DocumentsPanel's `payload.old` handler sees almost nothing.
-- REPLICA IDENTITY FULL ships the whole row.
-- ---------------------------------------------------------------------------

alter table public.documents replica identity full;

-- ---------------------------------------------------------------------------
-- 4) Add tables to the Realtime publication idempotently.
--
-- `alter publication ... add table` errors if the table is already a member,
-- which makes phase2/phase5 fail on a re-run.
-- ---------------------------------------------------------------------------

do $$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'room_messages'
  ) then
    alter publication supabase_realtime add table public.room_messages;
  end if;

  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'documents'
  ) then
    alter publication supabase_realtime add table public.documents;
  end if;
end
$$;

-- ---------------------------------------------------------------------------
-- 5) Backfill room owner roles, in case phase4 ran before some rooms existed.
-- ---------------------------------------------------------------------------

update public.room_members rm
set role = 'owner'
from public.rooms r
where r.id = rm.room_id and r.owner_id = rm.user_id and rm.role <> 'owner';
