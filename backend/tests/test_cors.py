"""CORS regression on the real FastAPI app; no lifespan/cloud/provider calls."""

import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.conversation_service import SessionPage


ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


class CorsTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.cloud = SimpleNamespace(
            mongodb=SimpleNamespace(database=object()),
            qdrant=SimpleNamespace(client=object()),
        )
        self.stack.enter_context(patch.object(app.state, "cloud_connections", self.cloud, create=True))
        # No TestClient context manager: don't run the cloud-connecting lifespan.
        self.stack.enter_context(patch("app.main.CloudConnections", side_effect=AssertionError("No cloud startup")))
        self.sessions = self.stack.enter_context(patch("app.api.sessions.create_conversation_service"))
        self.sessions.return_value.list_sessions.return_value = SessionPage([], 0, 50, 0)
        self.documents = self.stack.enter_context(patch("app.api.documents.create_document_service"))
        self.documents.return_value.list_documents.return_value = []
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_gets_echo_exact_allowed_origins_and_preserve_response_shapes(self):
        for origin in ORIGINS:
            for path in ("/sessions", "/documents"):
                with self.subTest(origin=origin, path=path):
                    response = self.client.get(path, headers={"Origin": origin})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers["Access-Control-Allow-Origin"], origin)
                    self.assertIn("Origin", response.headers["Vary"])
                    self.assertNotIn("Access-Control-Allow-Credentials", response.headers)
                    self.assertEqual(response.json(), [] if path == "/documents" else
                                     {"items": [], "offset": 0, "limit": 50, "total": 0})

    def test_chat_stream_preflight_allows_post_content_type_without_service_calls(self):
        for origin in ORIGINS:
            response = self.client.options("/chat/stream", headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["Access-Control-Allow-Origin"], origin)
            self.assertIn("POST", response.headers["Access-Control-Allow-Methods"].split(", "))
            self.assertIn("content-type", response.headers["Access-Control-Allow-Headers"].lower())
            self.assertNotIn("Access-Control-Allow-Credentials", response.headers)
        self.sessions.assert_not_called()
        self.documents.assert_not_called()

    def test_other_origins_are_not_allowed_including_wrong_scheme_port_and_suffix(self):
        for origin in ("http://localhost:3001", "https://localhost:3000",
                       "http://localhost:3000.evil.test", "https://example.test", "null"):
            with self.subTest(origin=origin):
                response = self.client.options("/chat/stream", headers={
                    "Origin": origin, "Access-Control-Request-Method": "POST",
                })
                self.assertEqual(response.status_code, 400)
                self.assertNotIn("Access-Control-Allow-Origin", response.headers)
                simple = self.client.get("/documents", headers={"Origin": origin})
                self.assertEqual(simple.status_code, 200)  # CORS isn't authentication.
                self.assertNotIn("Access-Control-Allow-Origin", simple.headers)

    def test_unknown_method_or_header_is_rejected_by_preflight(self):
        for method, header in (("TRACE", "content-type"), ("POST", "authorization")):
            response = self.client.options("/chat/stream", headers={
                "Origin": ORIGINS[0], "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": header,
            })
            self.assertEqual(response.status_code, 400)
        self.sessions.assert_not_called()
        self.documents.assert_not_called()

    def test_non_browser_get_is_unchanged(self):
        response = self.client.get("/sessions")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_handled_dependency_and_validation_errors_have_cors_headers(self):
        self.cloud.mongodb.database = None
        for response, status in (
            (self.client.get("/sessions", headers={"Origin": ORIGINS[0]}), 503),
            (self.client.post("/chat/stream", json={}, headers={"Origin": ORIGINS[0]}), 422),
        ):
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.headers["Access-Control-Allow-Origin"], ORIGINS[0])
        self.sessions.assert_not_called()
        self.documents.assert_not_called()


if __name__ == "__main__":
    unittest.main()
