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


async def stream_chat_completion(history: list[dict]) -> AsyncGenerator[str, None]:
    """
    history: list of {"role": "user"|"assistant", "content": str}, oldest first.
    Yields text chunks as they arrive from Groq.
    """
    client = get_client()
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]

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
