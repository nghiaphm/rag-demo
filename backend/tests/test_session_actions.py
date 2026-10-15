"""Repository guards for Session Actions; in-memory collections, no cloud/provider."""
import unittest
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.sessions import router

from app.conversation_models import SessionRecord, utc_now
from app.conversation_repository import MongoConversationRepository, SessionGenerationConflictError


class SessionCollection:
    def __init__(self, record):
        self.value = record.model_dump(by_alias=True)
        self.race = False
        self.updates = 0

    def find_one(self, query):
        return deepcopy(self.value) if self.value.get("_id") == query.get("_id") else None

    def find_one_and_update(self, query, update, **kwargs):
        self.updates += 1
        if self.race:
            self.value.update(active_generation_id=str(uuid4()), active_generation_started_at=utc_now())
        if any(self.value.get(key) != value for key, value in query.items()):
            return None
        self.value.update(update["$set"])
        return deepcopy(self.value)


class MessageCollection:
    def __init__(self):
        self.count = 2
        self.deletes = 0

    def delete_many(self, query):
        self.deletes += 1
        count = self.count
        self.count = 0
        return SimpleNamespace(deleted_count=count)


class SessionActionsRepositoryTests(unittest.TestCase):
    def fixture(self, active=False):
        record = SessionRecord(**({"active_generation_id": str(uuid4()), "active_generation_started_at": utc_now()} if active else {}))
        sessions, messages = SessionCollection(record), MessageCollection()
        return record, sessions, messages, MongoConversationRepository({"sessions": sessions, "messages": messages})

    def test_active_generation_prevents_delete_without_mutation(self):
        record, sessions, messages, repository = self.fixture(active=True)
        with self.assertRaises(SessionGenerationConflictError):
            repository.delete_session(record.session_id)
        self.assertEqual(sessions.updates, 0)
        self.assertEqual(messages.deletes, 0)

    def test_generation_race_is_stopped_by_atomic_delete_predicate(self):
        record, sessions, messages, repository = self.fixture()
        sessions.race = True
        with self.assertRaises(SessionGenerationConflictError):
            repository.delete_session(record.session_id)
        self.assertIsNone(sessions.value["deleted_at"])
        self.assertEqual(messages.deletes, 0)

    def test_repeat_delete_retains_tombstone_and_retries_message_cleanup(self):
        record, sessions, messages, repository = self.fixture()
        first = repository.delete_session(record.session_id)
        second = repository.delete_session(record.session_id)
        self.assertFalse(first.already_deleted)
        self.assertTrue(second.already_deleted)
        self.assertEqual((first.deleted_messages, second.deleted_messages), (2, 0))
        self.assertEqual(first.session.deleted_at, second.session.deleted_at)
        self.assertEqual(messages.deletes, 2)
        self.assertEqual(sessions.updates, 1)

    def test_rename_during_generation_preserves_the_guard(self):
        record, sessions, messages, repository = self.fixture(active=True)
        renamed = repository.update_title(record.session_id, "New title")
        self.assertEqual(renamed.title, "New title")
        self.assertEqual(renamed.active_generation_id, record.active_generation_id)
        self.assertEqual(messages.deletes, 0)

    def test_delete_generation_conflict_maps_to_http409(self):
        app = FastAPI()
        app.include_router(router)
        app.state.cloud_connections = SimpleNamespace(mongodb=SimpleNamespace(database=object()))
        service = SimpleNamespace(delete_session=lambda _: (_ for _ in ()).throw(SessionGenerationConflictError()))
        with patch("app.api.sessions.create_conversation_service", return_value=service):
            client = TestClient(app)
            response = client.delete(f"/sessions/{uuid4()}")
            client.close()
        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
