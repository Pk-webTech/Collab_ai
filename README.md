# Collaborative AI Workspace — Phase 1 (Foundation)

Personal AI workspace: auth, personal chat, message persistence. Built entirely
on free tiers — Supabase (Postgres + Auth, free project) and Groq (free LLM API).
Runs locally for now.

## What's included in this phase

- **Auth**: Supabase email/password auth (frontend), verified server-side via JWT (backend).
- **Personal chat**: create conversations, send messages, streamed AI replies.
- **Persistence**: every message (user + assistant) stored in Postgres.
- **Isolation groundwork**: `pgvector` extension enabled and RLS policies in
  place now, so Phase 3 (RAG) and Phase 2 (group rooms) don't need a schema
  rewrite later.

Not yet built (later phases): group rooms/WebSockets, document upload/RAG,
citations/abstention, caching, memory, multi-agent tools, deployment.

## 1. Create free accounts (5 min)

1. **Supabase** — [supabase.com](https://supabase.com) → New project (free tier).
   - In the SQL Editor, paste and run `db/schema.sql`.
   - Project Settings → API: copy `Project URL` and `anon public` key.
   - Project Settings → API → JWT Settings: copy the `JWT Secret`.
   - Project Settings → Database: copy the connection string (URI). Use the
     "Session pooler" one for `DATABASE_URL`.
2. **Groq** — [console.groq.com/keys](https://console.groq.com/keys) → create a
   free API key.

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
db/schema.sql          Supabase tables + RLS policies
frontend/
  app/page.tsx           Sign in / sign up
  app/chat/page.tsx        Conversation list + streaming chat UI
  lib/supabase.ts        Browser Supabase client
  lib/api.ts               Typed calls to the FastAPI backend
```

## Roadmap (from the system design doc)

| Phase | Focus |
|---|---|
| 1 ✅ | Foundation — auth, personal chat, persistence |
| 2 | Group rooms, invites, WebSockets, presence |
| 3 | Document upload + RAG (pgvector retrieval) |
| 4 | Citations, abstention, source viewer, permissions |
| 5 | Redis caching, parallel retrieval, background workers |
| 6 | Memory, tool calling, optional multi-agent workflows |
| 7 | Observability, rate limits, security hardening, deployment |

Free-tier services planned for later phases: Upstash Redis (Phase 5),
Supabase Storage (Phase 3, for uploaded documents), Vercel + Render free
tiers (Phase 7, when you're ready to deploy).
