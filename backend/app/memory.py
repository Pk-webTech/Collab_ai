"""
Automatic long-term memory. After a personal chat message is answered, a
background task asks the model to pull out one durable fact worth
remembering (if any) and stores it. Best-effort throughout: any failure
here is swallowed so it can never break the chat response itself.
"""
import os

from .llm import get_client
from .db import get_pool

MAX_MEMORIES = 50  # keep the table (and the prompt it feeds) small

EXTRACTION_PROMPT = (
    "You extract durable facts worth remembering about a user from a single "
    "chat message, for a personal AI assistant's long-term memory. Only "
    "extract stable facts: preferences, identity details, ongoing projects, "
    "constraints, relationships -- not one-off questions, small talk, or "
    "anything obviously temporary. Respond with ONE short sentence stating "
    "the fact in third person (e.g. 'Prefers concise answers.', 'Works as a "
    "nurse.'). If there's no durable fact worth remembering, respond with "
    "exactly: NONE"
)


async def _extract_fact(user_message: str) -> str | None:
    client = get_client()
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": user_message},
        ],
        max_tokens=60,
        temperature=0,
    )
    text = (response.choices[0].message.content or "").strip()
    if not text or text.upper().startswith("NONE"):
        return None
    return text


async def extract_and_store_memory(owner_id: str, user_message: str) -> None:
    try:
        fact = await _extract_fact(user_message)
        if not fact:
            return

        pool = get_pool()
        existing = await pool.fetch(
            "select content from user_memories where owner_id = $1", owner_id
        )
        if any(e["content"].strip().lower() == fact.strip().lower() for e in existing):
            return  # exact duplicate, skip

        await pool.execute(
            "insert into user_memories (owner_id, content) values ($1, $2)",
            owner_id,
            fact,
        )

        # Keep the table bounded -- drop the oldest beyond MAX_MEMORIES.
        await pool.execute(
            """
            delete from user_memories
            where owner_id = $1
            and id not in (
                select id from user_memories
                where owner_id = $1
                order by created_at desc
                limit $2
            )
            """,
            owner_id,
            MAX_MEMORIES,
        )
    except Exception:
        pass