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


class NonDestructiveHealthTests(unittest.TestCase):
    def test_concurrent_check_health_never_closes_live_mongo_or_qdrant_clients(self):
        from concurrent.futures import ThreadPoolExecutor

        mongo_creations = 0
        qdrant_creations = 0

        def mongo_factory(*_args, **kwargs):
            nonlocal mongo_creations
            mongo_creations += 1
            return FakeMongoClient(**kwargs)

        def qdrant_factory(**kwargs):
            nonlocal qdrant_creations
            qdrant_creations += 1
            return FakeQdrantClient(**kwargs)

        mongo = MongoDBConnection(make_settings(), mongo_factory)
        qdrant = QdrantConnection(make_settings(), qdrant_factory)

        # Initial startup connect
        self.assertTrue(mongo.connect().ok)
        self.assertTrue(qdrant.connect().ok)
        initial_mongo_client = mongo.client
        initial_qdrant_client = qdrant.client

        with ThreadPoolExecutor(max_workers=8) as pool:
            mongo_results = list(pool.map(lambda _: mongo.check_health(), range(24)))
            qdrant_results = list(pool.map(lambda _: qdrant.check_health(), range(24)))

        self.assertTrue(all(r.ok for r in mongo_results))
        self.assertTrue(all(r.ok for r in qdrant_results))
        self.assertIs(mongo.client, initial_mongo_client)
        self.assertIs(qdrant.client, initial_qdrant_client)
        self.assertFalse(initial_mongo_client.closed)
        self.assertFalse(initial_qdrant_client.closed)
        self.assertEqual(mongo_creations, 1)
        self.assertEqual(qdrant_creations, 1)

        # Even on transient ping failure, check_health must NOT close active pool
        initial_mongo_client.error = ServerSelectionTimeoutError("transient blip")
        initial_qdrant_client.error = ResponseHandlingException(TimeoutError("transient blip"))
        self.assertFalse(mongo.check_health().ok)
        self.assertFalse(qdrant.check_health().ok)
        self.assertFalse(initial_mongo_client.closed)
        self.assertFalse(initial_qdrant_client.closed)

    def test_dependency_health_required_vs_optional_matrix(self):
        import json
        from types import SimpleNamespace
        from unittest.mock import patch

        import app.main as main_mod
        from app.infrastructure.connections import CloudConnections
        from app.infrastructure.status import ConnectionStatus

        async def inline_threadpool(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        def run_coro(coro):
            try:
                coro.send(None)
                raise AssertionError("Expected synchronous completion with inline threadpool")
            except StopIteration as done:
                return done.value

        # 1. Default config (redis & s3 disabled): only mongodb & qdrant checked -> 200
        cfg_default = make_settings(rate_limit_enabled=False, async_ingestion_enabled=False, storage_backend="local")
        cc = CloudConnections(cfg_default)
        cc.mongodb = MongoDBConnection(cfg_default, lambda *_a, **kw: FakeMongoClient(**kw))
        cc.qdrant = QdrantConnection(cfg_default, lambda **kw: FakeQdrantClient(**kw))
        cc.connect_all()
        initial_mongo = cc.mongodb.client

        with (
            patch.object(main_mod, "run_in_threadpool", inline_threadpool),
            patch.object(main_mod, "settings", cfg_default),
            patch.object(main_mod.app.state, "cloud_connections", cc, create=True),
        ):
            resp = run_coro(main_mod.dependency_health())
        body = json.loads(resp.body)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(set(body["dependencies"]), {"mongodb", "qdrant"})
        self.assertFalse(initial_mongo.closed)

        # 2. RATE_LIMIT_ENABLED=true ONLY + Redis down -> warning in dependencies.redis, overall 200 ok!
        cfg_rl = make_settings(rate_limit_enabled=True, async_ingestion_enabled=False, storage_backend="local")
        cc_rl = CloudConnections(
            cfg_rl,
            redis_checker=lambda _cfg: ConnectionStatus("redis", False, "connection_failed", "Không thể kết nối Redis."),
        )
        cc_rl.mongodb = MongoDBConnection(cfg_rl, lambda *_a, **kw: FakeMongoClient(**kw))
        cc_rl.qdrant = QdrantConnection(cfg_rl, lambda **kw: FakeQdrantClient(**kw))
        cc_rl.connect_all()

        with (
            patch.object(main_mod, "run_in_threadpool", inline_threadpool),
            patch.object(main_mod, "settings", cfg_rl),
            patch.object(main_mod.app.state, "cloud_connections", cc_rl, create=True),
        ):
            resp_rl = run_coro(main_mod.dependency_health())
        body_rl = json.loads(resp_rl.body)
        self.assertEqual(resp_rl.status_code, 200)
        self.assertEqual(body_rl["status"], "ok")
        self.assertFalse(body_rl["dependencies"]["redis"]["ok"])

        # 3. ASYNC_INGESTION_ENABLED=true + Redis down -> 503 degraded
        cfg_async = make_settings(rate_limit_enabled=False, async_ingestion_enabled=True, storage_backend="local")
        cc_async = CloudConnections(
            cfg_async,
            redis_checker=lambda _cfg: ConnectionStatus("redis", False, "timeout", "Redis không phản hồi trong thời hạn."),
        )
        cc_async.mongodb = MongoDBConnection(cfg_async, lambda *_a, **kw: FakeMongoClient(**kw))
        cc_async.qdrant = QdrantConnection(cfg_async, lambda **kw: FakeQdrantClient(**kw))
        cc_async.connect_all()

        with (
            patch.object(main_mod, "run_in_threadpool", inline_threadpool),
            patch.object(main_mod, "settings", cfg_async),
            patch.object(main_mod.app.state, "cloud_connections", cc_async, create=True),
        ):
            resp_async = run_coro(main_mod.dependency_health())
        body_async = json.loads(resp_async.body)
        self.assertEqual(resp_async.status_code, 503)
        self.assertEqual(body_async["status"], "degraded")
        self.assertFalse(body_async["dependencies"]["redis"]["ok"])

        # 4. STORAGE_BACKEND=s3 + S3 down -> 503 degraded
        cfg_s3 = make_settings(storage_backend="s3", s3_bucket="demo-bucket")
        cc_s3 = CloudConnections(
            cfg_s3,
            s3_checker=lambda _cfg: ConnectionStatus("s3", False, "connection_failed", "Không thể kết nối S3."),
        )
        cc_s3.mongodb = MongoDBConnection(cfg_s3, lambda *_a, **kw: FakeMongoClient(**kw))
        cc_s3.qdrant = QdrantConnection(cfg_s3, lambda **kw: FakeQdrantClient(**kw))
        cc_s3.connect_all()

        with (
            patch.object(main_mod, "run_in_threadpool", inline_threadpool),
            patch.object(main_mod, "settings", cfg_s3),
            patch.object(main_mod.app.state, "cloud_connections", cc_s3, create=True),
        ):
            resp_s3 = run_coro(main_mod.dependency_health())
        body_s3 = json.loads(resp_s3.body)
        self.assertEqual(resp_s3.status_code, 503)
        self.assertEqual(body_s3["status"], "degraded")
        self.assertFalse(body_s3["dependencies"]["s3"]["ok"])


if __name__ == "__main__":
    unittest.main()
