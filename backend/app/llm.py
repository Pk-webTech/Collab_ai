"""
Groq client, prompts, and streaming chat completion (with optional tools).

Latency notes:
- Tool routing and the answer happen in ONE streaming call. Text is forwarded
  to the client the moment Groq produces it. Only if the model decides to
  call a tool do we make a second (also streaming) call with the results.
  Previously the first call was non-streaming, so for most messages the user
  saw nothing until the entire answer had been generated.
- `fast_model()` returns a smaller model for side jobs (memory extraction)
  that don't need the big model. Set GROQ_FAST_MODEL to enable it; if unset
  it falls back to GROQ_MODEL so nothing breaks.
"""
import json
import logging
import os
from typing import AsyncGenerator

from groq import AsyncGroq, BadRequestError

from .tools import TOOLS_SCHEMA, call_tool

logger = logging.getLogger("app.llm")

DEFAULT_MODEL = "llama-3.3-70b-versatile"
TEMPERATURE = 0.4

_client: AsyncGroq | None = None


def get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
    return _client


def main_model() -> str:
    return os.environ.get("GROQ_MODEL") or DEFAULT_MODEL


def fast_model() -> str:
    return os.environ.get("GROQ_FAST_MODEL") or main_model()


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


def _build_messages(
    history: list[dict], context: str | None, memories: list[str] | None
) -> list[dict]:
    system_content = SYSTEM_PROMPT
    if memories:
        system_content += MEMORY_INSTRUCTIONS + "\n".join(f"- {m}" for m in memories)
    if context:
        system_content += CONTEXT_INSTRUCTIONS + context
    return [{"role": "system", "content": system_content}, *history]


async def _stream_text(client: AsyncGroq, model: str, messages: list[dict]) -> AsyncGenerator[str, None]:
    """Plain streaming completion, no tools."""
    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        temperature=TEMPERATURE,
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


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
    model = main_model()
    messages = _build_messages(history, context, memories)

    if not use_tools:
        async for text in _stream_text(client, model, messages):
            yield text
        return

    # --- Pass 1: stream with tools available -------------------------------
    # Text deltas go straight to the caller. Tool-call deltas arrive in
    # fragments (id / name / arguments split across chunks) and are
    # stitched together per tool-call index.
    pending: dict[int, dict] = {}
    preamble: list[str] = []
    yielded_anything = False

    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto",
            stream=True,
            temperature=TEMPERATURE,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if delta.content:
                preamble.append(delta.content)
                yielded_anything = True
                yield delta.content

            for tc in delta.tool_calls or []:
                slot = pending.setdefault(tc.index, {"id": None, "name": "", "arguments": ""})
                if tc.id:
                    slot["id"] = tc.id
                fn = tc.function
                if fn is not None:
                    if fn.name:
                        slot["name"] += fn.name
                    if fn.arguments:
                        slot["arguments"] += fn.arguments
    except BadRequestError:
        # Groq returns 400 ("tool_use_failed") when a model produces a
        # malformed tool call. If nothing has reached the user yet, quietly
        # answer without tools instead of failing the whole reply.
        if yielded_anything:
            raise
        logger.warning("tool_stream_failed_falling_back_to_plain", exc_info=True)
        async for text in _stream_text(client, model, messages):
            yield text
        return

    calls = [slot for _, slot in sorted(pending.items()) if slot["name"]]
    if not calls:
        return  # the answer was already streamed in full

    # --- Run the tools, then pass 2: stream the final answer ---------------
    for i, slot in enumerate(calls):
        slot["id"] = slot["id"] or f"call_{i}"

    messages.append(
        {
            "role": "assistant",
            "content": "".join(preamble) or None,
            "tool_calls": [
                {
                    "id": slot["id"],
                    "type": "function",
                    "function": {"name": slot["name"], "arguments": slot["arguments"] or "{}"},
                }
                for slot in calls
            ],
        }
    )
    for slot in calls:
        try:
            arguments = json.loads(slot["arguments"] or "{}")
        except json.JSONDecodeError:
            arguments = {}
        result = call_tool(slot["name"], arguments)
        messages.append({"role": "tool", "tool_call_id": slot["id"], "content": result})

    if preamble:
        yield "\n\n"

    async for text in _stream_text(client, model, messages):
        yield text