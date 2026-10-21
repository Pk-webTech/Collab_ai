# Collaborative AI Workspace

**Live project: [collab-ai-frontend.onrender.com](https://collab-ai-frontend.onrender.com)**

[Open the workspace](https://collab-ai-frontend.onrender.com/chat) · [GitHub repository](https://github.com/Pk-webTech/Collab_ai)

A self-hosted AI workspace where individuals and teams chat with an assistant
that is grounded in their own documents. Personal conversations stay private;
shared rooms let a group talk to the same assistant over the same material, in
real time.

The live frontend and backend are hosted on Render’s free plan, with Supabase
for authentication and data, and Groq for AI responses. Document embeddings run
on the backend CPU. Hosting and provider costs depend on usage and plan limits.

> **First visit:** free services sleep when idle. Allow around 1–2 minutes or
> longer for the backend to wake and load its embedding model, then retry if needed.

---

## What it does

**Interactive interface.** Responsive desktop and mobile layouts, clickable
prompt starters, searchable conversation history, Markdown-formatted replies,
copy feedback, an expanding message composer, and document drag-and-drop.
Press Enter to send or Shift+Enter for a new line.

**Personal chat.** Create conversations, send messages, and get streamed replies
token by token. Everything is persisted to Postgres, so history survives
reloads and sessions.

**Group rooms.** Create a room and share its six-character join code. Anyone
with the code can join. Messages sync to every member instantly, and a presence
indicator shows who is currently online. Prefix a message with `@ai` to bring
the assistant into the conversation — its reply is persisted and broadcast to
the whole room like any other message.

**Document grounding (RAG).** Upload a `.txt`, `.md`, or `.pdf` (up to 5 MB) to
your personal workspace or to a room. The text is extracted, split into
overlapping chunks, and embedded locally. Every subsequent message searches
those documents by vector similarity and, when something relevant turns up,
feeds it to the model as context before it answers.

**Scoped retrieval.** Personal documents are searchable only in your own
conversations. Room documents are shared with, and searchable by, every member
of that room. The two never mix.

**Citations.** When a reply draws on retrieved documents, the exact chunks it
used are stored alongside it. A collapsible "Sources" line under the reply
shows the filenames and expands to the underlying snippets, so any claim can be
traced back to its origin. Citations persist across reloads rather than
existing only for the live response.

**Abstention.** The system prompt directs the model to say what is missing
rather than filling gaps, and to state things as fact only when they are
grounded in the conversation, the retrieved documents, or general knowledge it
is confident in.

**Long-term memory.** After each personal reply, a background call extracts one
durable fact worth remembering — a preference, an ongoing project, a
constraint — and stores it. A Memory panel shows everything remembered so far;
entries can be edited, added, or removed by hand. Capped at the 50 most recent
facts. Memory is personal-only and is never passed into room replies, so one
member's facts cannot leak to others.

**Tool calling.** The assistant can call a calculator and a clock mid-reply via
function calling, in both personal chat and room replies. Both run locally.

**Room permissions.** Room creators are owners; everyone else who joins is a
member. Owners can rename or delete the room and remove members. Members can
leave. Enforced in the backend against the verified JWT, with row-level
security in the database as a second line of defense.

---

## Architecture

```
┌─────────────────┐         ┌──────────────────┐
│  Next.js app    │────────▶│  FastAPI backend │
│  (browser)      │  REST   │  (Python)        │
└────────┬────────┘         └────────┬─────────┘
         │                           │
         │ Realtime (WebSocket)      │ SQL
         │                           │
         ▼                           ▼
   ┌──────────────────────────────────────┐        ┌──────────┐
   │  Supabase: Postgres + pgvector       │        │  Groq    │
   │  Auth, Realtime, row-level security  │        │  (LLM)   │
   └──────────────────────────────────────┘        └──────────┘
                                                   ┌──────────┐
                                                   │  Redis   │
                                                   │ (cache)  │
                                                   └──────────┘
```

**Authentication.** The browser authenticates against Supabase Auth and sends
the resulting JWT to the backend, which verifies it on every request — via
Supabase's JWKS endpoint for asymmetric tokens, falling back to the legacy
shared secret for older projects. No session state is kept server-side.

**Real-time sync.** Group chat and live upload status use Supabase Realtime
subscriptions directly from the browser, so there is no WebSocket server to
run or scale. The backend writes to Postgres; Postgres change events fan out to
every subscribed client.

**Retrieval.** Embeddings are computed locally with `all-MiniLM-L6-v2` (384
dimensions) and stored in a `pgvector` column with an IVFFlat index for cosine
similarity. Query embedding runs in a worker thread so it never blocks the
event loop. Results are cached in Redis per scope and query when configured.

**Background work.** Document chunking and embedding, AI replies in rooms, and
memory extraction all run after their HTTP response is sent, so no request
blocks on slow work. Uploads return immediately with status `processing` and
flip to `ready` over Realtime when indexing completes.

**Two layers of authorization.** The backend connects as the `postgres` role
and enforces ownership and membership itself using the verified JWT. Row-level
security policies independently govern any direct reads the browser makes
through Supabase, including Realtime subscriptions.

---

## Tech stack

| Layer      | Choice                                                 |
| ---------- | ------------------------------------------------------ |
| Frontend   | Next.js 16 (App Router), React 18, TypeScript          |
| Backend    | FastAPI, Python 3.11+, `asyncpg`                       |
| Database   | Postgres 15 with `pgvector` (Supabase)                 |
| Auth       | Supabase Auth (JWT, verified server-side)              |
| Real-time  | Supabase Realtime (Postgres change subscriptions)      |
| LLM        | Groq (`openai/gpt-oss-120b` in the live deployment)     |
| Embeddings | `sentence-transformers`, `all-MiniLM-L6-v2`, local CPU |
| Cache      | Redis (optional; Upstash free tier)                    |

---

## Getting started

### Prerequisites

- Python 3.11 or newer
- Node.js 20.9 or newer
- A Supabase project, a Groq API key, and optionally a Redis URL

### 1. Provision services

**Supabase** — create a project at [supabase.com](https://supabase.com), then in
the SQL Editor run `db/schema.sql` first, followed by `phase2_schema.sql`,
`phase3_schema.sql`, `phase4_schema.sql`, `phase5_schema.sql`,
`phase6_schema.sql`, `phase8_fixes.sql`, and `Phase9_performance .sql`.
Do not sort these alphabetically: the base schema must run first.

Collect four values:

| Value             | Where to find it                                 |
| ----------------- | ------------------------------------------------ |
| Project URL       | Settings → API                                   |
| `anon` public key | Settings → API                                   |
| JWT secret        | Settings → API → JWT Settings                    |
| Connection string | Settings → Database (use the Session pooler URI) |

Under Database → Replication, confirm `room_messages` and `documents` appear in
the `supabase_realtime` publication. The migrations add them, but this is what
makes live sync work, so it is worth a glance.

**Groq** — create a key at
[console.groq.com/keys](https://console.groq.com/keys). Groq's catalog changes
over time; confirm your chosen model is currently served:

```bash
curl https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY"
```

**Redis (optional)** — any Redis instance, or a free database at
[upstash.com](https://upstash.com). Leave `REDIS_URL` blank to run without
caching; nothing else depends on it.

### 2. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # fill in the values from step 1
uvicorn main:app --reload --port 8000
```

Verify with `curl http://localhost:8000/health` → `{"status":"ok"}`.

On first start the backend downloads the embedding model (~90 MB, cached
afterward) and loads it before accepting traffic, so startup takes a few
seconds. This is deliberate: loading it lazily on the first upload stalls
concurrent requests.

### 3. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) and sign up.

---

## Configuration

### Backend (`backend/.env`)

| Variable                             | Required | Description                                        |
| ------------------------------------ | -------- | -------------------------------------------------- |
| `SUPABASE_URL`                       | yes      | Project URL                                        |
| `SUPABASE_ANON_KEY`                  | yes      | Sent as the `apikey` header when fetching the JWKS |
| `DATABASE_URL`                       | yes      | Postgres connection string (Session pooler)        |
| `GROQ_API_KEY`                       | yes      | Groq API key                                       |
| `SUPABASE_JWT_SECRET`                | no       | Legacy HS256 fallback for older projects           |
| `GROQ_MODEL`                         | no       | Set explicitly; live deployment uses `openai/gpt-oss-120b` |
| `REDIS_URL`                          | no       | Enables retrieval caching when set                 |
| `FRONTEND_ORIGIN`                    | no       | Single allowed CORS origin                         |
| `FRONTEND_ORIGINS`                   | no       | Comma-separated origins; takes priority            |
| `LOG_LEVEL`                          | no       | `DEBUG`, `INFO`, `WARNING`, `ERROR`                |
| `CHAT_RATE_LIMIT_PER_MINUTE`         | no       | Default 20                                         |
| `ROOM_MESSAGE_RATE_LIMIT_PER_MINUTE` | no       | Default 30                                         |
| `UPLOAD_RATE_LIMIT_PER_MINUTE`       | no       | Default 10                                         |

### Frontend (`frontend/.env.local`)

| Variable                        | Description       |
| ------------------------------- | ----------------- |
| `NEXT_PUBLIC_SUPABASE_URL`      | Project URL       |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `anon` public key |
| `NEXT_PUBLIC_API_URL`           | Backend base URL  |

---

## API

All routes require `Authorization: Bearer <supabase-jwt>`.

| Method   | Path                               | Description                                     |
| -------- | ---------------------------------- | ----------------------------------------------- |
| `GET`    | `/health`                          | Liveness check (unauthenticated)                |
| `GET`    | `/api/conversations`               | List your conversations                         |
| `POST`   | `/api/conversations`               | Create a conversation                           |
| `GET`    | `/api/conversations/{id}/messages` | Message history with citations                  |
| `POST`   | `/api/chat`                        | Send a message; streams NDJSON delta/error/done events |
| `GET`    | `/api/rooms`                       | List rooms you belong to                        |
| `POST`   | `/api/rooms`                       | Create a room                                   |
| `POST`   | `/api/rooms/join`                  | Join by code                                    |
| `PATCH`  | `/api/rooms/{id}`                  | Rename (owner only)                             |
| `DELETE` | `/api/rooms/{id}`                  | Delete (owner only)                             |
| `GET`    | `/api/rooms/{id}/members`          | List members                                    |
| `DELETE` | `/api/rooms/{id}/members/{uid}`    | Leave, or remove a member (owner)               |
| `GET`    | `/api/rooms/{id}/messages`         | Room history                                    |
| `POST`   | `/api/rooms/{id}/messages`         | Post a message; `@ai` triggers a reply          |
| `GET`    | `/api/documents`                   | List documents (`?room_id=` for a room)         |
| `POST`   | `/api/documents/upload`            | Upload and index a file                         |
| `DELETE` | `/api/documents/{id}`              | Delete a document and its chunks                |
| `GET`    | `/api/memories`                    | List remembered facts                           |
| `POST`   | `/api/memories`                    | Add a fact                                      |
| `PATCH`  | `/api/memories/{id}`               | Edit a fact                                     |
| `DELETE` | `/api/memories/{id}`               | Delete a fact                                   |

Interactive docs are available at `/docs` while the backend is running.

---

## Operations

**Logging.** Every request emits one structured line with method, path, status,
duration, and a request id echoed back as `X-Request-ID`. Unhandled errors are
logged with a full traceback server-side; clients receive only a generic 500.

**Rate limiting.** Per-user sliding-window limits on chat messages, room
messages, and uploads. In-memory, so limits reset on restart and apply per
instance — appropriate for a single-instance deployment.

**Security headers.** `X-Frame-Options`, `X-Content-Type-Options`,
`Referrer-Policy`, and `Permissions-Policy` are set on both frontend and
backend responses. CORS is restricted to explicit methods and headers rather
than wildcards.

**Fail-fast startup.** Missing required environment variables raise a clear
error at boot rather than a confusing failure mid-request.

---

## Deployment

Both services are deployed on Render using the repository’s `render.yaml` Blueprint.

| Service | Public URL |
| --- | --- |
| Website | [collab-ai-frontend.onrender.com](https://collab-ai-frontend.onrender.com) |
| Backend API | [collab-ai-backend-n5x1.onrender.com](https://collab-ai-backend-n5x1.onrender.com) |
| Backend health | [Health check](https://collab-ai-backend-n5x1.onrender.com/health) |

The backend root URL is an API host, not a webpage; use `/health` to check readiness.

### Deploy your own copy

1. Connect your repository to Render and create a Blueprint using `render.yaml`.
2. Supply the Supabase URL, public anon key, database connection string, and Groq
   API key through Render environment settings. Never commit `.env` files.
3. The backend uses Python 3.12.10, CPU-only PyTorch, and FastAPI. The frontend
   uses Node.js 22 and a production Next.js build. Build and start commands are
   defined in the Blueprint.
4. Replace the Blueprint’s `NEXT_PUBLIC_API_URL` with your assigned backend URL
   and `FRONTEND_ORIGINS` with your frontend origin. These values currently point
   to the live project above. Rebuild the frontend when changing `NEXT_PUBLIC_*`.
5. In Supabase → Authentication → URL Configuration, set your frontend as the
   Site URL and add the required redirect URLs for email confirmation flows.

### AI model configuration

The live deployment explicitly sets both `GROQ_MODEL` and `GROQ_FAST_MODEL` to
`openai/gpt-oss-120b`. Validate both models against your own Groq account before
using them. A healthy backend does not by itself confirm that AI generation
works: test a streamed chat reply after deployment.

### Free-plan behavior and document limits

Render’s free services sleep when idle. Waking the backend also loads the
embedding model, so first requests can take around 1–2 minutes or longer.

PDF support extracts embedded text; it does not perform OCR. Scanned,
handwritten, or poorly encoded PDFs can produce empty or garbled text. Upload a
searchable PDF or a clean `.txt`/`.md` version for reliable document summaries.

---

## Project structure

```
backend/
  main.py                     App setup, CORS, lifespan, error handling
  app/
    auth.py                   Supabase JWT verification
    db.py                     Postgres pool, pgvector and jsonb codecs
    llm.py                    Groq client, prompts, streaming, tool calls
    retrieval.py              Vector search and caching
    embeddings.py             Local sentence-transformers model
    chunking.py               Overlapping text splitter
    extract.py                Text extraction (txt/md/pdf)
    memory.py                 Background fact extraction
    tools.py                  Calculator and clock
    cache.py                  Optional Redis helper
    ratelimit.py              Per-user sliding-window limiter
    middleware.py             Request logging, security headers
    logging_config.py         Structured stdout logging
    routers/                  conversations, chat, rooms, documents, memories
db/                           SQL migrations, run in filename order
frontend/
  app/
    page.tsx                  Sign in and sign up
    chat/page.tsx             Conversation list and streaming chat
    rooms/page.tsx            Create and join rooms
    rooms/[roomId]/page.tsx   Group chat, presence, permissions
  components/
    DocumentsPanel.tsx        Upload, list, delete; live status
    SourcesList.tsx           Collapsible citation viewer
    MemoryPanel.tsx           View and edit remembered facts
  lib/
    supabase.ts               Browser Supabase client
    api.ts                    Typed backend client
render.yaml                   Render Blueprint
```

---

## Troubleshooting

**Backend exits at startup.** A required environment variable is missing; the
error names it.

**Every API call fails with a CORS error.** `FRONTEND_ORIGINS` does not include
the origin the browser is loading from.

**Chat fails while streaming.** The API sends newline-delimited JSON events:
`delta` contains text, `error` reports generation or persistence failures, and
`done` confirms that the reply was saved. Deploy the frontend and backend
together. The UI reports interrupted streams; backend logs contain details.

**Uploads stay on `processing`.** The background indexing task failed. Check
the log for `document_processing_failed`.

**The assistant says it cannot find something that is in a document.** Check
that the document indexed into a sensible number of chunks:

```sql
select d.filename, d.status, d.char_count, count(dc.id) as chunks
from documents d
left join document_chunks dc on dc.document_id = d.id
group by d.id, d.filename, d.status, d.char_count;
```

A few thousand characters should yield single-digit chunks. If the count is in
the hundreds, the document was indexed before a chunker fix — delete and
re-upload it. If chunking looks right, the similarity threshold
(`MAX_DISTANCE` in `retrieval.py`) may be too strict.

**Duplicate requests in development.** React Strict Mode mounts effects twice.
This does not happen in production builds.

## Verification

### Windows startup after environment repair

From the project root, run `./start-backend.ps1` in one PowerShell terminal and
`./start-frontend.ps1` in another. These use the fresh `backend/.venv-runtime`
environment and the production frontend build. Open `http://localhost:3000`.
After frontend edits, run `npm --prefix frontend run build` before starting it.
The old `backend/.venv` is preserved but is not used by these scripts.

To recreate this environment on another machine:

```powershell
py -3.12 -m venv backend/.venv-runtime
backend/.venv-runtime/Scripts/python.exe -m pip install -r backend/requirements.txt
```

### Checks

Run `npm run typecheck`, `npm test`, and `npm run build` from `frontend/`.
Run `python -m unittest discover -s tests -v` from `backend/` after installing
its requirements. Regression tests mock database/model operations and never
write to your live project. `python check_services.py` performs read-only
checks of the database schema, Supabase Auth, and Groq model access.
`python check_runtime.py` also tests local embeddings and database vector
operations, and makes one short Groq completion request using synthetic text.

If a Windows Python environment refers to a missing interpreter, create a new
environment with an installed Python 3.11 or 3.12 interpreter, install
`requirements.txt`, and use it to start the backend. For locked Next.js build
output, stop the process holding it or set `NEXT_BUILD_DIR=.next-verify` for
both build and start commands.
