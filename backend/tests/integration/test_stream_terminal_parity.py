"""Real SSE/persistence parity regression, deterministic offline providers."""
import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.api.routes.chat import _encode_provider_stream
from app.conversations.service import ConversationService
from app.chat.pipeline import ProviderStreamChunk
from tests.integration.test_chat_persistence import FakeMessageRepository


class StreamTerminalParityTests(unittest.TestCase):
    def verify_error_parity(self, content):
        repository = FakeMessageRepository()
        service = ConversationService(repository)
        turn = service.begin_streaming_turn(
            session_id=str(uuid4()), question="Offline parity fixture", model="qa/mock"
        )

        usage = {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3}

        async def provider(_prepared):
            if content is not None:
                yield ProviderStreamChunk(content=content, usage=usage)
            raise RuntimeError("synthetic provider failure")

        async def collect():
            with patch("app.api.routes.chat.astream_rag_answer", provider):
                return [frame async for frame in _encode_provider_stream(
                    request_id=turn.request_id, prepared=SimpleNamespace(sources=[]),
                    service=service, turn=turn,
                )]

        frames = asyncio.run(collect())
        data = [json.loads(frame.split("data: ", 1)[1]) for frame in frames]
        terminal = data[-1]
        persisted = repository.finalized[-1]
        self.assertIsNone(repository.active_request_id)
        self.assertEqual(persisted.content, content or "")
        self.assertEqual(persisted.error_code, terminal["error"]["code"])
        self.assertEqual(terminal["status"], persisted.status.value)
        self.assertEqual(persisted.status.value, "PARTIAL" if content and content.strip() else "FAILED")
        self.assertEqual(data[0]["request_id"], persisted.request_id)
        self.assertEqual(data[0]["session_id"], persisted.session_id)
        self.assertEqual(data[0]["assistant_message_id"], persisted.message_id)
        self.assertEqual([event["sequence"] for event in data], list(range(1, len(data) + 1)))
        self.assertEqual(terminal["usage"], None if content is None else usage)
        self.assertEqual(None if persisted.usage is None else persisted.usage.model_dump(), terminal["usage"])

    def test_content_error_terminal_matches_persisted_partial(self):
        self.verify_error_parity("  partial\n\t")

    def test_no_delta_error_terminal_matches_persisted_failed(self):
        self.verify_error_parity(None)

    def test_whitespace_only_error_terminal_matches_persisted_status(self):
        self.verify_error_parity(" \n\t ")

    def test_unicode_whitespace_error_preserves_exact_content_and_usage(self):
        for content in (" ", "\t\r\n", "\u2003\u00a0"):
            with self.subTest(content=repr(content)):
                self.verify_error_parity(content)

    def test_whitespace_disconnect_persists_failed_and_releases_guard(self):
        repository = FakeMessageRepository()
        service = ConversationService(repository)
        turn = service.begin_streaming_turn(
            session_id=str(uuid4()), question="Cancel whitespace fixture", model="qa/mock"
        )
        content = " \n\t "
        usage = {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3}

        async def provider(_prepared):
            yield ProviderStreamChunk(content=content, usage=usage)

        async def disconnect():
            with patch("app.api.routes.chat.astream_rag_answer", provider):
                stream = _encode_provider_stream(
                    request_id=turn.request_id, prepared=SimpleNamespace(sources=[]),
                    service=service, turn=turn,
                )
                frames = [await anext(stream) for _ in range(3)]
                self.assertTrue(frames[-1].startswith("event: delta\n"))
                await stream.aclose()

        asyncio.run(disconnect())
        stored = repository.finalized[-1]
        self.assertEqual(stored.status.value, "FAILED")
        self.assertEqual(stored.content, content)
        self.assertEqual(stored.error_code, "RAG_STREAM_CANCELLED")
        self.assertEqual(stored.usage.model_dump(), usage)
        self.assertEqual(stored.request_id, turn.request_id)
        self.assertEqual(stored.session_id, turn.assistant_message.session_id)
        self.assertEqual(stored.message_id, turn.assistant_message.message_id)
        self.assertIsNone(repository.active_request_id)

    def test_whitespace_only_normal_finish_is_failed_empty_with_exact_content(self):
        repository = FakeMessageRepository()
        service = ConversationService(repository)
        turn = service.begin_streaming_turn(
            session_id=str(uuid4()), question="Whitespace-only normal finish", model="qa/mock"
        )
        parts = [" ", "\n\t"]

        async def provider(_prepared):
            for part in parts:
                yield ProviderStreamChunk(content=part, usage=None)

        async def collect():
            with patch("app.api.routes.chat.astream_rag_answer", provider):
                return [frame async for frame in _encode_provider_stream(
                    request_id=turn.request_id, prepared=SimpleNamespace(sources=[]),
                    service=service, turn=turn,
                )]

        frames = asyncio.run(collect())
        data = [json.loads(frame.split("data: ", 1)[1]) for frame in frames]
        self.assertEqual([event["content"] for event in data if "content" in event], parts)
        self.assertTrue(frames[-1].startswith("event: error\n"))
        self.assertEqual(data[-1]["status"], "FAILED")
        self.assertEqual(data[-1]["error"]["code"], "RAG_STREAM_EMPTY")
        persisted = repository.finalized[-1]
        self.assertEqual(persisted.content, "".join(parts))
        self.assertEqual(persisted.status.value, data[-1]["status"])
        self.assertEqual(persisted.error_code, data[-1]["error"]["code"])
        self.assertIsNone(repository.active_request_id)
