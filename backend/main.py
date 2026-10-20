import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

from app.logging_config import configure_logging

configure_logging()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.db import init_pool, close_pool
from app.routers import conversations, chat, rooms, documents, memories
from app import cache
from app.middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware

logger = logging.getLogger("app.startup")

# Fail fast with a clear message rather than a confusing error mid-request
# if the deployment is missing something it needs.
REQUIRED_ENV_VARS = ["SUPABASE_URL", "SUPABASE_ANON_KEY", "DATABASE_URL", "GROQ_API_KEY"]


def _validate_env() -> None:
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Check your .env (local) or your host's environment variable settings (deployed)."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_env()
    await init_pool()
    # Warm the embedding model before serving traffic. Importing torch holds
    # the GIL for several seconds even from a worker thread, which stalls
    # every concurrent request if it happens on the first upload instead.
    from app.embeddings import _get_model
    try:
        await asyncio.to_thread(_get_model)
        logger.info("startup_complete")
        yield
    finally:
        await cache.close()
        await close_pool()


app = FastAPI(title="Collaborative AI Workspace API", lifespan=lifespan)

# Accepts either a single FRONTEND_ORIGIN or a comma-separated
# FRONTEND_ORIGINS (useful once there's a deployed frontend domain in
# addition to localhost during development).
_origins_raw = os.environ.get("FRONTEND_ORIGINS") or os.environ.get(
    "FRONTEND_ORIGIN", "http://localhost:3000"
)
FRONTEND_ORIGINS = [o.strip() for o in _origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Never leak internals (stack traces, DB errors, etc.) to the client --
    # log the full detail server-side and return a generic message.
    logging.getLogger("app.error").exception("unhandled_exception path=%s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(conversations.router)
app.include_router(chat.router)
app.include_router(rooms.router)
app.include_router(documents.router)
app.include_router(memories.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
