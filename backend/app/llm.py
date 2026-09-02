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
    "You are the assistant inside a collaborative AI workspace. "
    "Be direct, concise, and helpful. Never state something as fact unless "
    "it comes from the conversation, the retrieved documents below (if any), "
    "or general knowledge you're confident in. If you don't know something "
    "or the available information doesn't cover it, say so plainly instead "
    "of guessing or filling gaps with plausible-sounding details."
)

CONTEXT_INSTRUCTIONS = (
    "\n\nThe following excerpts were retrieved from documents the user has "
    "uploaded, because they may be relevant to the latest message. If they "
    "answer the question, base your answer on them and mention which "
    "source(s) you drew from by filename. If they only partially answer it, "
    "say what's missing rather than filling the gap yourself. If they aren't "
    "relevant, ignore them and answer normally -- don't force a connection.\n\n"
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
