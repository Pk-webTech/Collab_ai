"""
Automatic long-term memory. After a personal chat message is answered, a
background task asks the model to pull out one durable fact worth
remembering (if any) and stores it. Best-effort throughout: any failure
here is swallowed so it can never break the chat response itself.

Uses the small/fast model (GROQ_FAST_MODEL): this is a one-sentence
classification job, and keeping it off the big model saves Groq rate limit
for the replies users are actually waiting on.
"""
import logging

from .llm import get_client, fast_model
from .db import get_pool

logger = logging.getLogger("app.memory")

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
    response = await client.chat.completions.create(
        model=fast_model(),
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

        # Insert only if an identical fact (case/whitespace-insensitive) isn't
        # already stored -- done in SQL instead of loading every memory into
        # Python and comparing there.
        inserted = await pool.fetchval(
            """
            insert into user_memories (owner_id, content)
            select $1::uuid, $2::text
            where not exists (
                select 1 from user_memories
                where owner_id = $1::uuid and lower(trim(content)) = lower(trim($2::text))
            )
            returning id
            """,
            owner_id,
            fact,
        )
        if inserted is None:
            return  # exact duplicate, skip

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
        # Still best-effort, but leave a trace so silent failures can be found.
        logger.warning("memory_extraction_failed owner_id=%s", owner_id, exc_info=True)