# Collaborative AI Workspace — Phase 1 + 2

Personal + group AI workspace. Built entirely on free tiers — Supabase
(Postgres + Auth + Realtime, free project) and Groq (free LLM API). Runs
locally for now.

## What's included

**Phase 1 — Foundation**

- **Auth**: Supabase email/password auth (frontend), verified server-side via JWT (backend).
- **Personal chat**: create conversations, send messages, streamed AI replies.
- **Persistence**: every message (user + assistant) stored in Postgres.
- **Isolation groundwork**: `pgvector` extension enabled and RLS policies in
  place now, so Phase 3 (RAG) doesn't need a schema rewrite later.

**Phase 2 — Group Collaboration**

- **Rooms**: create a room (gets a 6-character join code) or join one with a code.
- **Real-time sync**: new messages appear for every member instantly via
  **Supabase Realtime** (Postgres change subscriptions) — no backend
  WebSocket server needed.
- **Presence**: sidebar shows who's currently online in the room (Supabase
  Realtime Presence, client-side only).
- **AI in group chat**: any message starting with `@ai` triggers an
  assistant reply, persisted and broadcast to the whole room like any other message.

**Phase 3 — Documents + RAG**

- **Upload**: drop a `.txt`, `.md`, or `.pdf` (≤5MB) into your personal
  workspace or into a room. Text is extracted, chunked, and embedded
  **locally** (sentence-transformers, `all-MiniLM-L6-v2` — no embedding API
  key, fully free, runs on CPU).
- **Retrieval**: every chat message (personal or `@ai` in a room) searches
  the relevant documents by vector similarity (`pgvector`) and, if something
  relevant enough turns up, feeds it to the model as context before it
  answers.
- **Scoping**: personal documents are only searchable in your own personal
  chat; room documents are shared with and searchable by everyone in that room.

**Phase 4 — Trust Layer**

- **Citations**: every AI reply that used retrieved documents stores exactly
  which chunks it drew from. A collapsible "Sources" line under the reply
  shows the filenames, and expands to the actual snippets so you can verify
  the claim yourself — this persists across reloads, not just for the live response.
- **Abstention**: the system prompt now explicitly tells the model to say
  what's missing rather than filling gaps, and to only state things as fact
  when they're grounded in the conversation, the retrieved documents, or
  general knowledge it's confident in.
- **Room permissions**: room creators are now `owner`s, everyone else who
  joins is a `member`. Owners can rename or delete the room and remove
  members; members can leave. Enforced both in the backend (checked against
  the verified JWT) and via RLS as a second line of defense.

**Phase 5 — Performance**

- **Caching**: document-retrieval results are cached in Redis (free tier via
  Upstash) for 5 minutes per (scope, question) — repeated or near-duplicate
  questions, common in a group room, skip re-embedding and re-searching.
  Entirely optional: leave `REDIS_URL` unset and the app runs exactly as
  before, just without this layer.
- **Parallel retrieval**: fetching recent chat history and searching
  documents no longer happen one after another — they're independent reads,
  so both requests fire concurrently, cutting latency before the model even
  starts replying.
- **Background uploads**: uploading a document now returns immediately with
  status `processing`; chunking and embedding happen in a background task
  instead of blocking the request. The sidebar updates live to `ready` (or
  `failed`) via Realtime once it's done — no polling, no page refresh.

**Phase 6 — Memory & Tools**

- **Long-term memory**: after each personal chat reply, a background call
  asks the model to pull out one durable fact worth remembering (e.g.
  preferences, ongoing projects) and stores it — never blocking the reply
  itself. A "Memory" panel in the personal chat sidebar shows everything
  remembered so far; click any entry to edit it, or add your own. Capped at
  the 50 most recent facts. Memory is personal-only — it's never passed into
  group room replies, so one member's remembered facts can't leak to others.
- **Tool calling**: the assistant can call a calculator and a clock
  mid-reply via Groq's function calling (e.g. "what's 18% of 245?" or "what
  time is it in UTC?"), in both personal chat and `@ai` room replies. Both
  tools run locally — no external API, no extra cost.

Not yet built (later phases): multi-agent workflows, observability, rate
limits, security hardening, deployment.

## 1. Create free accounts (5 min)

1. **Supabase** — [supabase.com](https://supabase.com) → New project (free tier).
   - In the SQL Editor, paste and run `db/schema.sql`, then
     `db/phase2_schema.sql`, then `db/phase3_schema.sql`, then
     `db/phase4_schema.sql`, then `db/phase5_schema.sql`, then `db/phase6_schema.sql`.
   - Database → Replication: confirm `room_messages` is listed under the
     `supabase_realtime` publication (the schema script adds it, but it's
     worth a glance — this is what makes group chat update live).
   - Project Settings → API: copy `Project URL` and `anon public` key.
   - Project Settings → API → JWT Settings: copy the `JWT Secret`.
   - Project Settings → Database: copy the connection string (URI). Use the
     "Session pooler" one for `DATABASE_URL`.
2. **Groq** — [console.groq.com/keys](https://console.groq.com/keys) → create a
   free API key.
3. **Upstash Redis (optional)** — [upstash.com](https://upstash.com) → New
   database (free tier) → copy the `rediss://` connection string into
   `REDIS_URL`. Skip this and leave it blank if you don't want caching yet;
   nothing else depends on it.

> **First run note:** the first time you upload a document, the backend
> downloads the embedding model (~90MB, one-time, cached afterward) from
> Hugging Face — make sure the machine running the backend has internet
> access for that first request.

## 2. Backend setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then fill in the values from step 1
uvicorn main:app --reload --port 8000
```

Check it's up: `curl http://localhost:8000/health` → `{"status":"ok"}`.

## 3. Frontend setup

```bash
cd frontend
npm install
cp .env.local.example .env.local  # fill in Supabase URL + anon key
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) — sign up, then chat.

## Project layout

```
backend/
  main.py              FastAPI app, CORS, startup/shutdown
  app/auth.py           Verifies Supabase JWTs
  app/db.py              Postgres connection pool (asyncpg)
  app/llm.py              Groq streaming client
  app/routers/conversations.py
  app/routers/chat.py       Streams model output, persists messages
  app/routers/rooms.py       Rooms, join codes, group messages, @ai trigger
  app/routers/documents.py    Upload, list, delete documents
  app/routers/memories.py      Memory CRUD (list/add/edit/delete)
  app/embeddings.py         Local sentence-transformers embedding model
  app/chunking.py            Overlapping text chunker
  app/extract.py              Text extraction (txt/md/pdf)
  app/retrieval.py            Vector similarity search (pgvector) + Redis caching
  app/cache.py                 Optional Redis caching helper (Upstash free tier)
  app/memory.py                 Background fact extraction for long-term memory
  app/tools.py                   Calculator + clock, exposed to the model as tools
db/schema.sql          Phase 1 tables + RLS policies
db/phase2_schema.sql    Rooms, membership, room messages + Realtime publication
db/phase3_schema.sql    Documents, chunks, vector index + RLS
db/phase4_schema.sql    Citation storage, room roles + owner-only RLS
db/phase5_schema.sql    Realtime on documents (live upload-status updates)
db/phase6_schema.sql    Long-term memory table + RLS
frontend/
  app/page.tsx           Sign in / sign up
  app/chat/page.tsx        Personal conversation list + streaming chat UI
  app/rooms/page.tsx        Create/join rooms
  app/rooms/[roomId]/page.tsx   Group chat, live sync, presence, roles/permissions
  components/DocumentsPanel.tsx  Upload/list/delete docs, live status updates
  components/SourcesList.tsx      Collapsible citation viewer
  components/MemoryPanel.tsx       View/add/edit/delete remembered facts
  lib/supabase.ts        Browser Supabase client
  lib/api.ts               Typed calls to the FastAPI backend
```

## Roadmap (from the system design doc)

| Phase | Focus                                                      |
| ----- | ---------------------------------------------------------- |
| 1 ✅  | Foundation — auth, personal chat, persistence              |
| 2 ✅  | Group rooms, invites, realtime sync, presence              |
| 3 ✅  | Document upload + RAG (pgvector retrieval)                 |
| 4 ✅  | Citations, abstention, source viewer, permissions          |
| 5 ✅  | Redis caching, parallel retrieval, background workers      |
| 6 ✅  | Memory, tool calling                                       |
| 7     | Observability, rate limits, security hardening, deployment |

Free-tier services planned for later phases: Supabase Storage (raw file
retention, if you want it beyond extracted text), Vercel + Render free tiers
(Phase 7, when you're ready to deploy).
