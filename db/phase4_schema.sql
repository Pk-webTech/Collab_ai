-- Phase 4 schema: citation storage + room permissions (owner vs member).
-- Run this in the Supabase SQL editor AFTER schema.sql, phase2_schema.sql,
-- and phase3_schema.sql.

-- 1) Citations: store which document chunks backed each AI reply, so the
--    source list survives a page reload instead of only existing for the
--    live response.
alter table public.messages add column if not exists sources jsonb;
alter table public.room_messages add column if not exists sources jsonb;

-- 2) Room roles: the creator is 'owner', everyone else who joins is
--    'member'. Owners can rename/delete the room and remove members;
--    members can leave.
alter table public.room_members add column if not exists role text not null default 'member'
  check (role in ('owner', 'member'));

update public.room_members rm
set role = 'owner'
from public.rooms r
where r.id = rm.room_id and r.owner_id = rm.user_id and rm.role <> 'owner';

create or replace function public.handle_new_room()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.room_members (room_id, user_id, role) values (new.id, new.owner_id, 'owner');
  return new;
end;
$$;

-- Owner-only room management (frontend/direct-Supabase safety net; the
-- FastAPI backend enforces this too, using the verified JWT, before writing).
create policy "owner can update room" on public.rooms
  for update using (owner_id = auth.uid());

create policy "owner can delete room" on public.rooms
  for delete using (owner_id = auth.uid());

create policy "leave room or be removed by owner" on public.room_members
  for delete using (
    user_id = auth.uid()
    or exists (
      select 1 from public.rooms r
      where r.id = room_members.room_id and r.owner_id = auth.uid()
    )
  );
