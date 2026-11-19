"""Integration tests for POST/GET /sessions surface filtering and legacy compatibility."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.api.routes.sessions import router  # noqa: E402
from app.conversations.models import SessionRecord, SessionSurface  # noqa: E402
from app.conversations.service import SessionPage  # noqa: E402


class SessionSurfaceRouteTests(unittest.TestCase):
    @staticmethod
    def _make_app() -> FastAPI:
        app = FastAPI()
        app.include_router(router)
        app.state.cloud_connections = SimpleNamespace(
            mongodb=SimpleNamespace(database=object())
        )
        return app

    def test_post_and_get_sessions_forward_surface_and_reject_invalid_values(self) -> None:
        calls: list[tuple] = []

        class _FakeService:
            def create_session(self, *, title=None, surface=SessionSurface.WORKSPACE):
                calls.append(("create", title, surface))
                return SessionRecord(title=title or "Mới", surface=surface)

            def list_sessions(self, *, offset=0, limit=50, surface=None):
                calls.append(("list", offset, limit, surface))
                item = SessionRecord(
                    title="HR item",
                    surface=surface or SessionSurface.WORKSPACE,
                )
                return SessionPage([item], offset, limit, 1)

        client = TestClient(self._make_app())
        with patch("app.api.routes.sessions.create_conversation_service", return_value=_FakeService()):
            hr_created = client.post("/sessions", json={"surface": "hr", "title": "HR Policy"})
            ws_listed = client.get("/sessions?offset=0&limit=20&surface=workspace")
            hr_listed = client.get("/sessions?offset=0&limit=20&surface=hr")

        self.assertEqual(hr_created.status_code, 201)
        self.assertEqual(hr_created.json()["surface"], "hr")
        self.assertEqual(ws_listed.status_code, 200)
        self.assertEqual(ws_listed.json()["items"][0]["surface"], "workspace")
        self.assertEqual(hr_listed.status_code, 200)
        self.assertEqual(hr_listed.json()["items"][0]["surface"], "hr")
        self.assertEqual(
            calls,
            [
                ("create", "HR Policy", SessionSurface.HR),
                ("list", 0, 20, SessionSurface.WORKSPACE),
                ("list", 0, 20, SessionSurface.HR),
            ],
        )

        invalid_query = client.get("/sessions?surface=unknown")
        invalid_body = client.post("/sessions", json={"surface": "unknown"})
        self.assertEqual(invalid_query.status_code, 422)
        self.assertEqual(invalid_body.status_code, 422)


if __name__ == "__main__":
    unittest.main()
