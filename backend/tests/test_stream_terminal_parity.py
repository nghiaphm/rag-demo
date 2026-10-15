"""F7-03-05 gate: real SSE encoder vs persistence, deterministic offline provider.

The whitespace-only error case intentionally exposes a pre-existing contract
mismatch. Do not change its expectation or application semantics to green QA.
"""
import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.api.chat import _encode_provider_stream
from app.conversation_service import ConversationService
from app.rag.pipeline import ProviderStreamChunk
from tests.test_chat_persistence import FakeMessageRepository


class StreamTerminalParityTests(unittest.TestCase):
    def verify_error_parity(self, content):
        repository = FakeMessageRepository()
        service = ConversationService(repository)
        turn = service.begin_streaming_turn(
            session_id=str(uuid4()), question="Offline parity fixture", model="qa/mock"
        )

        async def provider(_prepared):
            if content is not None:
                yield ProviderStreamChunk(content=content, usage=None)
            raise RuntimeError("synthetic provider failure")

        async def collect():
            with patch("app.api.chat.astream_rag_answer", provider):
                return [frame async for frame in _encode_provider_stream(
                    request_id=turn.request_id, prepared=SimpleNamespace(sources=[]),
                    service=service, turn=turn,
                )]

        frames = asyncio.run(collect())
        terminal = json.loads(frames[-1].split("data: ", 1)[1])
        persisted = repository.finalized[-1]
        self.assertIsNone(repository.active_request_id)
        self.assertEqual(persisted.content, content or "")
        self.assertEqual(persisted.error_code, terminal["error"]["code"])
        self.assertEqual(terminal["status"], persisted.status.value)

    def test_content_error_terminal_matches_persisted_partial(self):
        self.verify_error_parity("  partial\n\t")

    def test_no_delta_error_terminal_matches_persisted_failed(self):
        self.verify_error_parity(None)

    def test_whitespace_only_error_terminal_matches_persisted_status(self):
        self.verify_error_parity(" \n\t ")
