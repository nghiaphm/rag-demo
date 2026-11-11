"""Unit tests không dùng network cho cloud connection/error mapping."""

import unittest

import httpx
from pymongo.errors import OperationFailure, ServerSelectionTimeoutError
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app.infrastructure.mongo import MongoDBConnection
from app.infrastructure.qdrant import QdrantConnection
from app.shared.config import Settings


def make_settings(**overrides) -> Settings:
    values = {
        "groq_api_key": "test-groq",
        "openai_base_url": "https://api.groq.com/openai/v1",
        "embedding_api_key": "test-embedding",
        "mongodb_uri": "mongodb+srv://user:password@example.mongodb.net/",
        "mongodb_db_name": "rag_demo",
        "qdrant_url": "https://example.cloud.qdrant.io:6333",
        "qdrant_api_key": "test-qdrant",
        "mongodb_timeout_ms": 25,
        "qdrant_timeout_seconds": 0.025,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class FakeMongoClient:
    def __init__(self, error=None, **_kwargs):
        self.error = error
        self.options = _kwargs
        self.admin = self
        self.closed = False

    def command(self, _name):
        if self.error:
            raise self.error
        return {"ok": 1}

    def __getitem__(self, name):
        return {"name": name}

    def close(self):
        self.closed = True


class FakeQdrantClient:
    def __init__(self, error=None, **_kwargs):
        self.error = error
        self.closed = False

    def get_collections(self):
        if self.error:
            raise self.error
        return {"collections": []}

    def close(self):
        self.closed = True


class MongoDBConnectionTests(unittest.TestCase):
    def test_connect_success(self):
        connection = MongoDBConnection(
            make_settings(), lambda *args, **kwargs: FakeMongoClient(**kwargs)
        )
        self.assertEqual(connection.connect().code, "connected")
        self.assertIsNotNone(connection.database)
        self.assertIs(connection.client.options["tz_aware"], True)
        connection.close()

    def test_authentication_error_is_safe(self):
        error = OperationFailure("raw secret-bearing server error", code=8000)
        connection = MongoDBConnection(
            make_settings(), lambda *args, **kwargs: FakeMongoClient(error, **kwargs)
        )
        status = connection.connect()
        self.assertEqual(status.code, "authentication_failed")
        self.assertNotIn("secret-bearing", status.message)

    def test_timeout_error_is_safe(self):
        error = ServerSelectionTimeoutError("raw host details")
        connection = MongoDBConnection(
            make_settings(), lambda *args, **kwargs: FakeMongoClient(error, **kwargs)
        )
        status = connection.connect()
        self.assertEqual(status.code, "timeout")
        self.assertNotIn("host details", status.message)


class QdrantConnectionTests(unittest.TestCase):
    def test_connect_success(self):
        connection = QdrantConnection(make_settings(), FakeQdrantClient)
        self.assertEqual(connection.connect().code, "connected")
        connection.close()

    def test_authentication_error_is_safe(self):
        error = UnexpectedResponse(401, "Unauthorized", b"raw secret", httpx.Headers())
        connection = QdrantConnection(
            make_settings(), lambda **kwargs: FakeQdrantClient(error, **kwargs)
        )
        status = connection.connect()
        self.assertEqual(status.code, "authentication_failed")
        self.assertNotIn("raw secret", status.message)

    def test_timeout_error_is_safe(self):
        error = ResponseHandlingException(TimeoutError("raw endpoint"))
        connection = QdrantConnection(
            make_settings(), lambda **kwargs: FakeQdrantClient(error, **kwargs)
        )
        status = connection.connect()
        self.assertEqual(status.code, "timeout_or_network")
        self.assertNotIn("raw endpoint", status.message)


if __name__ == "__main__":
    unittest.main()
