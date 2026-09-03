-- Phase 5 schema: enable Realtime on `documents` so the frontend sees a
-- document's status flip from 'processing' to 'ready' (or 'failed') live,
-- once the new background task (see app/routers/documents.py) finishes
-- chunking + embedding it. No new tables -- `status` already existed from
-- Phase 3, this just publishes changes to it.
-- Run this in the Supabase SQL editor AFTER schema.sql, phase2_schema.sql,
-- phase3_schema.sql, and phase4_schema.sql.

alter publication supabase_realtime add table public.documents;