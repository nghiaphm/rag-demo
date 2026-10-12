"""Tests cho P2-03 non-streaming message persistence và /chat compatibility."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.chat import router
from app.conversation_models import MessageRole, MessageStatus
from app.conversation_repository import SessionDeletedError, SessionNotFoundError
from app.conversation_service import ConversationService


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
                "answer": "Grounded answer",
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
        self.assertEqual(result["answer"], "Grounded answer")
        self.assertEqual((user.sequence, pending.sequence), (7, 8))
        self.assertEqual(user.request_id, completed.request_id)
        self.assertEqual(user.role, MessageRole.USER)
        self.assertEqual(completed.status, MessageStatus.COMPLETED)
        self.assertEqual(completed.content, "Grounded answer")
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

        with self.assertRaisesRegex(RuntimeError, "secret provider detail"):
            self.service.answer_with_persistence(
                session_id=self.session_id,
                question="Question",
                generate=fail,
                model="provider/model",
            )

        failed = self.repository.finalized[0]
        self.assertEqual(failed.status, MessageStatus.FAILED)
        self.assertEqual(failed.error_code, "RAG_PIPELINE_ERROR")
        self.assertNotIn("secret", failed.model_dump_json())
        self.assertEqual(failed.content, "")
        self.assertIsNotNone(failed.completed_at)
        self.assertIsNone(self.repository.active_request_id)

    def test_invalid_empty_generation_is_persisted_as_failed(self):
        with self.assertRaises(ValidationError):
            self.service.answer_with_persistence(
                session_id=self.session_id,
                question="Question",
                generate=lambda: {"answer": "", "sources": []},
                model="provider/model",
            )
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


class FakePersistentChatService:
    def __init__(self, error=None):
        self.error = error
        self.args = None

    def answer_with_persistence(self, **kwargs):
        self.args = kwargs
        if self.error is not None:
            raise self.error
        return kwargs["generate"]()


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
        with patch("app.api.chat.answer_question", return_value=self.result()), patch(
            "app.api.chat.create_conversation_service"
        ) as create_service:
            response = TestClient(self.make_app()).post(
                "/chat", json={"question": "Question"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.result())
        create_service.assert_not_called()

    def test_session_chat_uses_persistence_and_preserves_response_shape(self):
        session_id = str(uuid4())
        service = FakePersistentChatService()
        with patch("app.api.chat.answer_question", return_value=self.result()), patch(
            "app.api.chat.create_conversation_service", return_value=service
        ):
            response = TestClient(self.make_app()).post(
                "/chat", json={"question": "Question", "session_id": session_id}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.result())
        self.assertEqual(service.args["session_id"], session_id)
        self.assertEqual(service.args["question"], "Question")

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
                "app.api.chat.create_conversation_service",
                return_value=FakePersistentChatService(error),
            ):
                response = TestClient(self.make_app()).post(
                    "/chat",
                    json={"question": "Question", "session_id": str(uuid4())},
                )
            self.assertEqual(response.status_code, expected)


if __name__ == "__main__":
    unittest.main()
