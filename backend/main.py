from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from app.db import init_pool, close_pool
from app.routers import conversations, chat, rooms, documents, memories
from app import cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await cache.close()
    await close_pool()


app = FastAPI(title="Collaborative AI Workspace API", lifespan=lifespan)

frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(conversations.router)
app.include_router(chat.router)
app.include_router(rooms.router)
app.include_router(documents.router)
app.include_router(memories.router)


@app.get("/health")
async def health():
    return {"status": "ok"}