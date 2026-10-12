"""API tests cho P2-02 session CRUD, history và error contract."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.sessions import router
from app.conversation_models import (
    MessageRecord,
    MessageRole,
    MessageStatus,
    SessionRecord,
    utc_now,
)
from app.conversation_repository import (
    SessionDeleteResult,
    SessionDeletedError,
    SessionNotFoundError,
)
from app.conversation_service import MessagePage, SessionPage


class FakeConversationService:
    def __init__(self):
        self.session = SessionRecord(title="Original")
        self.request_id = str(uuid4())
        self.messages = [
            MessageRecord(
                session_id=self.session.session_id,
                sequence=1,
                role=MessageRole.USER,
                content="Question",
                status=MessageStatus.COMPLETED,
                request_id=self.request_id,
            ),
            MessageRecord(
                session_id=self.session.session_id,
                sequence=2,
                role=MessageRole.ASSISTANT,
                content="Answer",
                status=MessageStatus.COMPLETED,
                request_id=self.request_id,
            ),
        ]
        self.list_args = None
        self.history_args = None

    def create_session(self, *, title=None):
        if title is not None:
            self.session = self.session.model_copy(update={"title": title})
        return self.session

    def list_sessions(self, *, offset, limit):
        self.list_args = (offset, limit)
        return SessionPage([self.session], offset, limit, 1)

    def get_session(self, session_id):
        if session_id != self.session.session_id:
            raise SessionNotFoundError()
        return self.session

    def update_title(self, session_id, *, title):
        self.get_session(session_id)
        self.session = self.session.model_copy(
            update={"title": title, "updated_at": utc_now()}
        )
        return self.session

    def list_messages(self, session_id, *, offset, limit):
        self.get_session(session_id)
        self.history_args = (offset, limit)
        return MessagePage(self.messages[offset : offset + limit], offset, limit, 2)

    def delete_session(self, session_id):
        self.get_session(session_id)
        deleted = self.session.model_copy(update={"deleted_at": utc_now()})
        return SessionDeleteResult(deleted, len(self.messages), False)


class DeletedConversationService(FakeConversationService):
    def get_session(self, session_id):
        raise SessionDeletedError()

    def update_title(self, session_id, *, title):
        raise SessionDeletedError()

    def list_messages(self, session_id, *, offset, limit):
        raise SessionDeletedError()


class SessionApiTests(unittest.TestCase):
    @staticmethod
    def make_app(database=object()):
        app = FastAPI()
        app.include_router(router)
        app.state.cloud_connections = SimpleNamespace(
            mongodb=SimpleNamespace(database=database)
        )
        return app

    def test_create_list_get_update_history_and_delete(self):
        fake = FakeConversationService()
        session_id = fake.session.session_id
        with patch(
            "app.api.sessions.create_conversation_service", return_value=fake
        ):
            client = TestClient(self.make_app())
            created = client.post("/sessions", json={"title": "  New title  "})
            listed = client.get("/sessions?offset=0&limit=10")
            detail = client.get(f"/sessions/{session_id}")
            updated = client.patch(
                f"/sessions/{session_id}", json={"title": "  Renamed  "}
            )
            history = client.get(
                f"/sessions/{session_id}/messages?offset=1&limit=1"
            )
            deleted = client.delete(f"/sessions/{session_id}")

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["title"], "New title")
        self.assertEqual(created.json()["scope"]["mode"], "ALL_ACTIVE")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["total"], 1)
        self.assertEqual(fake.list_args, (0, 10))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(updated.json()["title"], "Renamed")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["items"][0]["sequence"], 2)
        self.assertEqual(history.json()["total"], 2)
        self.assertEqual(fake.history_args, (1, 1))
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["deleted_messages"], 2)
        self.assertEqual(deleted.json()["message_policy"], "hard_deleted")
        self.assertTrue(deleted.json()["tombstone_retained"])

    def test_missing_and_deleted_sessions_have_distinct_statuses(self):
        fake = FakeConversationService()
        with patch(
            "app.api.sessions.create_conversation_service", return_value=fake
        ):
            missing = TestClient(self.make_app()).get(f"/sessions/{uuid4()}")
        with patch(
            "app.api.sessions.create_conversation_service",
            return_value=DeletedConversationService(),
        ):
            deleted = TestClient(self.make_app()).get(
                f"/sessions/{fake.session.session_id}"
            )
            deleted_history = TestClient(self.make_app()).get(
                f"/sessions/{fake.session.session_id}/messages"
            )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(deleted.status_code, 410)
        self.assertEqual(deleted_history.status_code, 410)

    def test_invalid_inputs_are_rejected_before_service(self):
        client = TestClient(self.make_app())
        self.assertEqual(client.get("/sessions/not-a-uuid").status_code, 422)
        self.assertEqual(client.post("/sessions", json={"title": "   "}).status_code, 422)
        self.assertEqual(client.get("/sessions?limit=0").status_code, 422)

    def test_returns_503_without_exposing_dependency_details(self):
        response = TestClient(self.make_app(database=None)).get("/sessions")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("mongodb", response.text.lower())


if __name__ == "__main__":
    unittest.main()
