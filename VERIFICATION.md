# Project verification — 20 October 2026

## Fixed

- Personal chat renders streaming replies and guards against stale history loads
  and duplicate sends during conversation creation.
- Stream errors and database save failures reach the UI; completion is sent only
  after persistence. Frontend and backend must be deployed together because the
  stream now uses newline-delimited JSON.
- Signup shows email-confirmation instructions when no session is issued.
- Room sends display the returned message even when Realtime misses an event.
  Room/document polling recovers missed updates. Failed actions show errors.
- Document chunking no longer skips text after early paragraph boundaries.
- Retrieval cache keys include the current ready document set, preventing stale
  results after uploads and deletions. Redis has bounded network timeouts and
  corrupt cached JSON falls back to a cache miss.
- Calculator limits prevent excessive exponentiation; malformed tool arguments
  return errors rather than crashing a reply.
- Blank/oversized personal messages are rejected. PDF extraction runs off the
  event loop. Startup no longer requires the optional legacy JWT secret and
  closes resources on embedding startup failure.
- Setup documentation specifies the correct migration order. The unsupported
  lint command was replaced with an explicit TypeScript check.

## Checks completed

- Production Next.js build: passed, including static page generation.
- TypeScript check: passed.
- Backend regression tests: 10 passed, with database/model operations mocked.
- Frontend streaming regression tests: 3 passed, including split UTF-8, server
  errors, and interrupted streams.
- Groq read-only check: key accepted and configured main model listed.

## Live runtime and browser verification

- Rebuilt the full backend environment at `backend/.venv-runtime` using Python
  3.12. Dependency consistency check passed. The broken old `.venv` is preserved.
- All 10 backend regression tests pass in the repaired environment.
- The real embedding model loads and generates 384-dimensional vectors.
- Live Postgres vector codec, cosine search, and empty-scope retrieval pass.
- A real Groq streamed completion succeeds.
- Backend health returns 200, protected API calls without authentication return
  401, and the localhost frontend CORS preflight succeeds.
- User signed in successfully through the browser.
- Personal chat returned the correct calculator result (84) and survived reload.
- Uploaded the synthetic `workspace-smoke-test.txt` through the UI. It reached
  ready status; chat returned its exact code MARIGOLD-7429 and Thursday launch
  day, and the source panel displayed the matching text.
- Created an isolated verification room; its `@ai` reply succeeded and persisted
  after reload. A second browser tab received a new room message.
- Supabase Auth, required database columns, Realtime publication for documents
  and room messages, membership RLS helper, and RLS on nine tables pass checks.

## Running locally

Both services were started for verification: frontend at http://localhost:3000
and backend at http://127.0.0.1:8000. To restart later, run `./start-backend.ps1`
and `./start-frontend.ps1` in separate PowerShell terminals from the project root.
These scripts use the repaired environment and the production frontend build.

The test document, verification chat, and `Workspace verification — test room`
remain as identifiable test artifacts. Existing user data was not deleted.
The synthetic upload source is in `backend/tests/fixtures/`.

## Verification limits

A second independent user account was not available, so join-code access and
owner/member authorization across different accounts have not been exercised
end to end. New-account email confirmation and destructive UI actions were not
performed. Existing documents affected by the earlier chunking bug need
re-uploading. These checks establish that the core local flows work; they do
not guarantee absence of every bug or constitute a production security audit.

## Interactive UI verification — October 21, 2026

- Redesigned personal chat, room screens, document and memory panels, and sign-in.
- Added prompt starters, searchable conversation history, Markdown answers,
  copy feedback, expanding composer, upload dropzone, and responsive navigation.
- Production build and TypeScript validation pass; all 3 frontend streaming tests pass.
- Live browser check: prompt starter fills/focuses composer, synthetic chat returns
  a formatted numbered list, and copying an answer displays success feedback.
- Document library loads existing ready files; memory empty state and room shared
  library render. Existing room messages display after reload.
- Checked desktop at 1440x900 and mobile at 390x844. Mobile document view has no
  horizontal document overflow. Closed mobile sidebars are hidden from keyboard
  navigation and the accessibility tree.
- Service checks confirm database, Supabase Auth, and Groq connectivity.
- Destructive controls and account creation were not exercised during this UI pass.
