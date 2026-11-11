"""Tests cho P2-03 non-streaming message persistence và /chat compatibility."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.routes.chat import router
from app.conversations.models import MessageRole, MessageStatus
from app.conversations.repository import SessionDeletedError, SessionNotFoundError
from app.conversations.service import (
    ConversationGenerationError,
    ConversationService,
)


class FakeMessageRepository:
    def __init__(self):
        self.pair = None
        self.finalized = []
        self.active_request_id = None
        self.released = []

    def begin_generation(self, session_id, request_id):
        self.active_request_id = request_id
        return 7, 8

    def release_generation(self, session_id, request_id):
        self.released.append((session_id, request_id))
        self.active_request_id = None

    def create_message_pair(self, user, assistant):
        self.pair = (user, assistant)

    def mark_assistant_streaming(self, message):
        self.streaming = message
        return message

    def finalize_assistant_message(self, message):
        self.finalized.append(message)
        return message


class MessagePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.session_id = str(uuid4())
        self.document_id = str(uuid4())
        self.version_id = str(uuid4())
        self.chunk_id = str(uuid4())
        self.repository = FakeMessageRepository()
        self.service = ConversationService(self.repository)

    def test_user_and_pending_assistant_exist_before_successful_generation(self):
        def generate():
            user, assistant = self.repository.pair
            self.assertEqual(user.status, MessageStatus.COMPLETED)
            self.assertEqual(assistant.status, MessageStatus.PENDING)
            return {
                "answer": "Grounded answer [1]",
                "sources": [
                    {
                        "chunk_id": self.chunk_id,
                        "document_id": self.document_id,
                        "version_id": self.version_id,
                        "file_name": "guide.md",
                        "page": 0,
                    },
                    {"chunk_id": "invalid"},
                ],
            }

        result = self.service.answer_with_persistence(
            session_id=self.session_id,
            question="Question",
            generate=generate,
            model="provider/model",
        )

        user, pending = self.repository.pair
        completed = self.repository.finalized[0]
        self.assertEqual(result["answer"], "Grounded answer [1]")
        self.assertEqual(result["request_id"], user.request_id)
        self.assertEqual(result["user_message_id"], user.message_id)
        self.assertEqual(result["assistant_message_id"], pending.message_id)
        self.assertEqual(len(result["citations"]), 1)
        self.assertIsNone(result["usage"])
        self.assertEqual((user.sequence, pending.sequence), (7, 8))
        self.assertEqual(user.request_id, completed.request_id)
        self.assertEqual(user.role, MessageRole.USER)
        self.assertEqual(completed.status, MessageStatus.COMPLETED)
        self.assertEqual(completed.content, "Grounded answer [1]")
        self.assertEqual(completed.model, "provider/model")
        self.assertIsNone(completed.usage)
        self.assertEqual(len(completed.citations), 1)
        self.assertEqual(completed.citations[0].chunk_id, self.chunk_id)
        self.assertIsNotNone(completed.completed_at)
        self.assertIsNone(self.repository.active_request_id)
        self.assertEqual(self.repository.released[0][0], self.session_id)

    def test_generation_failure_is_persisted_without_raw_error(self):
        def fail():
            raise RuntimeError("secret provider detail")

        with self.assertRaises(ConversationGenerationError) as raised:
            self.service.answer_with_persistence(
                session_id=self.session_id,
                question="Question",
                generate=fail,
                model="provider/model",
            )
        self.assertIsInstance(raised.exception.__cause__, RuntimeError)
        self.assertNotIn("secret", str(raised.exception))

        failed = self.repository.finalized[0]
        self.assertEqual(failed.status, MessageStatus.FAILED)
        self.assertEqual(failed.error_code, "RAG_PIPELINE_ERROR")
        self.assertNotIn("secret", failed.model_dump_json())
        self.assertEqual(failed.content, "")
        self.assertIsNotNone(failed.completed_at)
        self.assertIsNone(self.repository.active_request_id)

    def test_invalid_empty_generation_is_persisted_as_failed(self):
        with self.assertRaises(ConversationGenerationError) as raised:
            self.service.answer_with_persistence(
                session_id=self.session_id,
                question="Question",
                generate=lambda: {"answer": "", "sources": []},
                model="provider/model",
            )
        self.assertIsInstance(raised.exception.__cause__, ValidationError)
        self.assertEqual(self.repository.finalized[0].status, MessageStatus.FAILED)
        self.assertIsNone(self.repository.active_request_id)

    def test_cancellation_is_failed_and_releases_guard(self):
        def cancel():
            raise asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            self.service.answer_with_persistence(
                session_id=self.session_id,
                question="Question",
                generate=cancel,
                model="provider/model",
            )
        failed = self.repository.finalized[0]
        self.assertEqual(failed.status, MessageStatus.FAILED)
        self.assertEqual(failed.error_code, "GENERATION_CANCELLED")
        self.assertIsNone(self.repository.active_request_id)

    def test_streaming_turn_records_active_and_truthful_terminal_states(self):
        turn = self.service.begin_streaming_turn(
            session_id=self.session_id, question="Question", model="provider/model"
        )
        self.assertEqual(turn.user_message.status, MessageStatus.COMPLETED)
        self.assertEqual(turn.assistant_message.status, MessageStatus.STREAMING)
        self.assertEqual(self.repository.pair[1].status, MessageStatus.PENDING)
        self.assertEqual(self.repository.streaming.status, MessageStatus.STREAMING)
        self.assertEqual(turn.user_message.request_id, turn.assistant_message.request_id)

        completed = self.service.finalize_streaming_turn(
            turn,
            content="Answer",
            sources=[],
            usage={"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
        )
        self.assertEqual(completed.status, MessageStatus.COMPLETED)
        self.assertEqual(completed.content, "Answer")
        self.assertEqual(completed.usage.total_tokens, 3)
        self.assertIsNone(self.repository.active_request_id)

    def test_streaming_failure_is_partial_only_when_content_exists(self):
        partial = self.service.begin_streaming_turn(
            session_id=self.session_id, question="Question", model="provider/model"
        )
        terminal = self.service.finalize_streaming_turn(
            partial,
            content="partial answer",
            sources=[],
            usage=None,
            error_code="RAG_STREAM_ERROR",
        )
        self.assertEqual(terminal.status, MessageStatus.PARTIAL)
        self.assertEqual(terminal.error_code, "RAG_STREAM_ERROR")

        failed = self.service.begin_streaming_turn(
            session_id=self.session_id, question="Question", model="provider/model"
        )
        terminal = self.service.finalize_streaming_turn(
            failed,
            content="",
            sources=[],
            usage=None,
            error_code="RAG_STREAM_EMPTY",
        )
        self.assertEqual(terminal.status, MessageStatus.FAILED)
        self.assertEqual(terminal.content, "")


class FakePersistentChatService:
    def __init__(self, error=None):
        self.error = error
        self.args = None

    def answer_with_persistence(self, **kwargs):
        self.args = kwargs
        if self.error is not None:
            raise self.error
        result = kwargs["generate"]()
        return {
            **result,
            "request_id": str(uuid4()),
            "user_message_id": str(uuid4()),
            "assistant_message_id": str(uuid4()),
            "citations": [],
            "usage": None,
        }


class ChatApiPersistenceTests(unittest.TestCase):
    @staticmethod
    def make_app(database=object(), qdrant=object()):
        app = FastAPI()
        app.include_router(router)
        app.state.cloud_connections = SimpleNamespace(
            mongodb=SimpleNamespace(database=database),
            qdrant=SimpleNamespace(client=qdrant),
        )
        return app

    @staticmethod
    def result():
        return {"answer": "Answer", "sources": []}

    def test_no_session_keeps_stateless_response_and_skips_persistence(self):
        with patch("app.api.routes.chat.answer_question", return_value=self.result()), patch(
            "app.api.routes.chat.create_conversation_service"
        ) as create_service:
            response = TestClient(self.make_app()).post(
                "/chat", json={"question": "Question"}
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["answer"], "Answer")
        self.assertEqual(body["sources"], [])
        self.assertEqual(body["citations"], [])
        self.assertEqual(body["metadata"]["mode"], "STATELESS")
        self.assertEqual(body["status"], "COMPLETED")
        self.assertIsNone(body["session_id"])
        self.assertIsNone(body["user_message_id"])
        self.assertIsNone(body["assistant_message_id"])
        self.assertIsNone(body["usage"])
        self.assertIsNone(body["error"])
        self.assertIsNotNone(body["request_id"])
        create_service.assert_not_called()

        # Legacy clients can keep projecting the two original fields unchanged.
        self.assertEqual(
            {key: body[key] for key in ("answer", "sources")},
            self.result(),
        )

    def test_no_result_fallback_has_no_sources_or_citations(self):
        result = {
            "answer": "Không tìm thấy thông tin trong tài liệu",
            "sources": [],
        }
        with patch("app.api.routes.chat.answer_question", return_value=result):
            response = TestClient(self.make_app()).post(
                "/chat", json={"question": "Outside corpus"}
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["answer"], result["answer"])
        self.assertEqual(body["sources"], [])
        self.assertEqual(body["citations"], [])
        self.assertIsNone(body["usage"])

    def test_multiple_documents_keep_candidates_and_verified_citations(self):
        first = {
            "chunk_id": str(uuid4()),
            "document_id": str(uuid4()),
            "version_id": str(uuid4()),
            "file_name": "first.md",
            "page": 0,
        }
        second = {
            "chunk_id": str(uuid4()),
            "document_id": str(uuid4()),
            "version_id": str(uuid4()),
            "file_name": "second.md",
            "page": 2,
        }
        result = {"answer": "Facts from both [1] and [2]", "sources": [first, second]}
        with patch("app.api.routes.chat.answer_question", return_value=result):
            response = TestClient(self.make_app()).post(
                "/chat", json={"question": "Compare documents"}
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["sources"]), 2)
        self.assertEqual(len(body["citations"]), 2)
        self.assertEqual(
            {item["document_id"] for item in body["citations"]},
            {first["document_id"], second["document_id"]},
        )

    def test_session_chat_uses_persistence_and_preserves_response_shape(self):
        session_id = str(uuid4())
        service = FakePersistentChatService()
        with patch(
            "app.api.routes.chat.answer_question", return_value=self.result()
        ) as answer, patch(
            "app.api.routes.chat.create_conversation_service", return_value=service
        ):
            response = TestClient(self.make_app()).post(
                "/chat", json={"question": "Question", "session_id": session_id}
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["answer"], "Answer")
        self.assertEqual(body["sources"], [])
        self.assertEqual(body["citations"], [])
        self.assertEqual(body["session_id"], session_id)
        self.assertIsNotNone(body["user_message_id"])
        self.assertIsNotNone(body["assistant_message_id"])
        self.assertEqual(body["metadata"]["mode"], "PERSISTENT")
        self.assertEqual(body["status"], "COMPLETED")
        self.assertIsNone(body["usage"])
        self.assertIsNone(body["error"])
        self.assertEqual(service.args["session_id"], session_id)
        self.assertEqual(service.args["question"], "Question")
        self.assertEqual(answer.call_args.kwargs["session_id"], session_id)

    def test_invalid_missing_and_deleted_session_contract(self):
        self.assertEqual(
            TestClient(self.make_app()).post(
                "/chat", json={"question": "Question", "session_id": "bad"}
            ).status_code,
            422,
        )
        for error, expected in (
            (SessionNotFoundError(), 404),
            (SessionDeletedError(), 410),
        ):
            with patch(
                "app.api.routes.chat.create_conversation_service",
                return_value=FakePersistentChatService(error),
            ):
                response = TestClient(self.make_app()).post(
                    "/chat",
                    json={"question": "Question", "session_id": str(uuid4())},
                )
            self.assertEqual(response.status_code, expected)

    def test_stateless_generation_failure_uses_safe_complete_envelope(self):
        with patch(
            "app.api.routes.chat.answer_question",
            side_effect=RuntimeError("secret provider detail"),
        ):
            response = TestClient(self.make_app()).post(
                "/chat", json={"question": "Question"}
            )
        self.assertEqual(response.status_code, 502)
        body = response.json()
        self.assertEqual(body["status"], "FAILED")
        self.assertIsNone(body["answer"])
        self.assertEqual(body["sources"], [])
        self.assertEqual(body["citations"], [])
        self.assertIsNone(body["usage"])
        self.assertEqual(body["metadata"]["mode"], "STATELESS")
        self.assertEqual(body["error"]["code"], "RAG_PIPELINE_ERROR")
        self.assertNotIn("secret", response.text)

    def test_persistent_generation_failure_preserves_durable_ids(self):
        session_id = str(uuid4())
        failure = ConversationGenerationError(
            request_id=str(uuid4()),
            user_message_id=str(uuid4()),
            assistant_message_id=str(uuid4()),
        )
        with patch(
            "app.api.routes.chat.create_conversation_service",
            return_value=FakePersistentChatService(failure),
        ):
            response = TestClient(self.make_app()).post(
                "/chat", json={"question": "Question", "session_id": session_id}
            )
        self.assertEqual(response.status_code, 502)
        body = response.json()
        self.assertEqual(body["request_id"], failure.request_id)
        self.assertEqual(body["user_message_id"], failure.user_message_id)
        self.assertEqual(body["assistant_message_id"], failure.assistant_message_id)
        self.assertEqual(body["session_id"], session_id)
        self.assertEqual(body["metadata"]["mode"], "PERSISTENT")
        self.assertEqual(body["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
