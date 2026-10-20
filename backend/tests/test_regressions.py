import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError

from app.chunking import chunk_text
from app.tools import calculate, call_tool
from app import cache, retrieval
from app.auth import CurrentUser
from app.routers import chat


class TextTests(unittest.TestCase):
    def test_chunk_boundaries_do_not_drop_text(self):
        text = "a" * 650 + "\n\n" + "IMPORTANT" + "b" * 1500
        chunks = chunk_text(text)
        self.assertTrue(any("IMPORTANT" in chunk for chunk in chunks))
        cursor = 0
        for chunk in chunks:
            start = text.find(chunk, max(0, cursor - 150))
            self.assertLessEqual(start, cursor)
            self.assertGreaterEqual(start, 0)
            cursor = start + len(chunk)
        self.assertEqual(cursor, len(text))

    def test_short_chunks_terminate(self):
        self.assertEqual(chunk_text("abc", 1, 100), ["a", "b", "c"])

    def test_calculator_limits_and_normal_math(self):
        self.assertEqual(calculate("12 * (3 + 4)"), "84")
        self.assertEqual(calculate("+2"), "2")
        for expression in ("9**999999999", "True + 1", "1 / 0", "(-1)**0.5", "1e309 * 2"):
            self.assertTrue(calculate(expression).startswith("Error:"))
        self.assertTrue(call_tool("calculate", []).startswith("Error:"))

    def test_blank_and_oversized_chat_rejected(self):
        for message in ("  ", "", "x" * 20001):
            with self.assertRaises(ValidationError):
                chat.ChatIn(conversation_id=uuid4(), message=message)


class AsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_corrupt_cache_is_a_miss(self):
        client = SimpleNamespace(get=AsyncMock(return_value="{broken"))
        with patch.object(cache, "_get_client", return_value=client):
            self.assertIsNone(await cache.get_json("key"))

    async def test_document_changes_change_cache_key(self):
        pool = SimpleNamespace(fetchval=AsyncMock(side_effect=["doc1", "", "doc2"]))
        hit = {"context": None, "sources": []}
        with patch.object(cache, "get_json", new=AsyncMock(return_value=hit)) as read, \
             patch.object(retrieval, "_embed", new=AsyncMock(return_value=[0.0])):
            owner_id = str(uuid4())
            for _ in range(3):
                await retrieval.retrieve_context(pool, owner_id=owner_id, room_id=None, query="test")
            self.assertEqual(len({call.args[0] for call in read.call_args_list}), 3)

    async def stream_response(self, *, fail_generation=False, fail_save=False, owns=True):
        pool = SimpleNamespace(
            fetchval=AsyncMock(return_value=uuid4() if owns else None),
            fetch=AsyncMock(return_value=[]),
            execute=AsyncMock(side_effect=RuntimeError("save failed") if fail_save else None),
        )
        async def generate(*args, **kwargs):
            yield "Hello 🌍"
            if fail_generation:
                raise RuntimeError("provider failed")

        with patch.object(chat, "get_pool", return_value=pool), \
             patch.object(chat, "retrieve_context", new=AsyncMock(return_value=retrieval.RetrievalResult(None, []))), \
             patch.object(chat, "stream_chat_completion", new=generate):
            response = await chat.send_message(
                chat.ChatIn(conversation_id=uuid4(), message="Hi"),
                BackgroundTasks(), CurrentUser(id=str(uuid4())),
            )
            events = [json.loads(line) async for line in response.body_iterator]
        return events, pool

    async def test_stream_done_only_after_save(self):
        events, pool = await self.stream_response()
        self.assertEqual([e["type"] for e in events], ["delta", "done"])
        pool.execute.assert_awaited_once()

    async def test_generation_failure_is_explicit(self):
        events, pool = await self.stream_response(fail_generation=True)
        self.assertEqual(events[-1]["type"], "error")
        pool.execute.assert_not_awaited()

    async def test_save_failure_is_explicit(self):
        events, _ = await self.stream_response(fail_save=True)
        self.assertEqual(events[-1]["type"], "error")

    async def test_foreign_conversation_rejected(self):
        with self.assertRaises(HTTPException) as error:
            await self.stream_response(owns=False)
        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
