import os
import json
from typing import AsyncGenerator
from groq import AsyncGroq

from .tools import TOOLS_SCHEMA, call_tool

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

MEMORY_INSTRUCTIONS = (
    "\n\nHere's what you remember about this user from past conversations. "
    "Use it to personalize your answer when it's actually relevant -- don't "
    "force it in, and don't recite it back verbatim unless asked.\n\n"
)


async def stream_chat_completion(
    history: list[dict],
    context: str | None = None,
    memories: list[str] | None = None,
    use_tools: bool = True,
) -> AsyncGenerator[str, None]:
    """
    history: list of {"role": "user"|"assistant", "content": str}, oldest first.
    context: optional retrieved-document text to ground the reply in (RAG).
    memories: optional list of remembered facts about the user (personal
      chat only -- never passed for group rooms, to avoid leaking one
      member's personal facts to the rest of the room).
    use_tools: if True, gives the model a calculator and a clock it can call
      before answering (see app/tools.py).
    Yields text chunks as they arrive from Groq.
    """
    client = get_client()
    model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

    system_content = SYSTEM_PROMPT
    if memories:
        system_content += MEMORY_INSTRUCTIONS + "\n".join(f"- {m}" for m in memories)
    if context:
        system_content += CONTEXT_INSTRUCTIONS + context

    messages = [{"role": "system", "content": system_content}, *history]

    if use_tools:
        # First pass, non-streaming: let the model decide whether it needs a
        # tool. Cheap and fast on Groq. If it doesn't need one, we already
        # have the full answer and just emit it directly (no benefit to a
        # second call); if it does, we run the tool(s) and stream the final
        # answer in a second call below.
        first = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto",
            temperature=0.4,
        )
        choice = first.choices[0].message

        if choice.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": choice.content,
                    "tool_calls": [tc.model_dump() for tc in choice.tool_calls],
                }
            )
            for tc in choice.tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                result = call_tool(tc.function.name, arguments)
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": result}
                )
            # Fall through to the streaming call below with tool results attached.
        elif choice.content:
            yield choice.content
            return

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