import os
from typing import AsyncGenerator
from groq import AsyncGroq

_client: AsyncGroq | None = None


def get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
    return _client


SYSTEM_PROMPT = (
    "You are the assistant inside a personal AI workspace. "
    "Be direct, concise, and helpful. If you don't know something, say so "
    "instead of guessing."
)

CONTEXT_INSTRUCTIONS = (
    "\n\nThe following excerpts were retrieved from documents the user has "
    "uploaded, because they may be relevant to the latest message. Use them "
    "if they help answer the question, and mention which source you drew "
    "from by filename. If they aren't relevant, ignore them and answer "
    "normally -- don't force a connection.\n\n"
)


async def stream_chat_completion(
    history: list[dict], context: str | None = None
) -> AsyncGenerator[str, None]:
    """
    history: list of {"role": "user"|"assistant", "content": str}, oldest first.
    context: optional retrieved-document text to ground the reply in (RAG).
    Yields text chunks as they arrive from Groq.
    """
    client = get_client()
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    system_content = SYSTEM_PROMPT
    if context:
        system_content += CONTEXT_INSTRUCTIONS + context

    messages = [{"role": "system", "content": system_content}, *history]

    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        temperature=0.4,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
