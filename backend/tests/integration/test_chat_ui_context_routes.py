"""Integration tests for context-aware HR ui_context forwarding across /chat and /chat/stream."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.api.routes.chat import router  # noqa: E402
from app.chat.events import ProviderStreamChunk  # noqa: E402
from app.chat.ui_context import UiPageContext  # noqa: E402
from app.conversations.models import MessageRecord, MessageRole, MessageStatus  # noqa: E402
from app.conversations.service import StreamingTurn  # noqa: E402
from app.shared.config import settings  # noqa: E402


class ChatUiContextRouteTests(unittest.TestCase):
    @staticmethod
    def _make_app() -> FastAPI:
        app = FastAPI()
        app.include_router(router)
        app.state.cloud_connections = SimpleNamespace(
            mongodb=SimpleNamespace(database=object()),
            qdrant=SimpleNamespace(client=object()),
        )
        return app

    @staticmethod
    def _parse_frames(response) -> list[tuple[str, dict]]:
        frames = []
        for frame in response.text.strip().split("\n\n"):
            event_line, data_line = frame.splitlines()
            frames.append(
                (
                    event_line.removeprefix("event: "),
                    json.loads(data_line.removeprefix("data: ")),
                )
            )
        return frames

    def test_chat_stream_forwards_hr_ui_context_across_all_three_routes_and_keeps_question_clean(self) -> None:
        client = TestClient(self._make_app())
        session_id = str(uuid4())

        for route, title in (
            ("/hr", "Tổng quan nhân sự"),
            ("/hr/documents", "Tài liệu nhân sự"),
            ("/hr/guide", "Hướng dẫn sử dụng"),
        ):
            captured_prepare: dict[str, object] = {}
            captured_turn_question: dict[str, str] = {}

            def fake_prepare_rag_stream(question, *, database, qdrant_client, session_id=None, ui_context=None):
                captured_prepare["question"] = question
                captured_prepare["ui_context"] = ui_context
                return SimpleNamespace(
                    sources=[
                        {
                            "chunk_id": str(uuid4()),
                            "document_id": str(uuid4()),
                            "version_id": str(uuid4()),
                            "file_name": "chinh-sach-nghi-phep.pdf",
                            "page": 0,
                        }
                    ]
                )

            async def fake_stream(_prepared):
                yield ProviderStreamChunk(
                    content=f"### 1. Giới thiệu trang hiện tại\nBạn đang ở {title} (`{route}`) [1].",
                    usage={"input_tokens": 12, "output_tokens": 20, "total_tokens": 32},
                )

            class _FakeService:
                def begin_streaming_turn(self, *, session_id, question, model, attachments=()):
                    captured_turn_question["value"] = question
                    request_id = str(uuid4())
                    user = MessageRecord(
                        session_id=session_id,
                        sequence=1,
                        role=MessageRole.USER,
                        content=question,
                        status=MessageStatus.COMPLETED,
                        request_id=request_id,
                    )
                    assistant = MessageRecord(
                        session_id=session_id,
                        sequence=2,
                        role=MessageRole.ASSISTANT,
                        status=MessageStatus.STREAMING,
                        model=model,
                        request_id=request_id,
                    )
                    return StreamingTurn(request_id, user, assistant)

                def finalize_streaming_turn(self, *_args, **_kwargs):
                    return None

            with patch.object(settings, "tool_use_enabled", False), patch(
                "app.api.routes.chat.prepare_rag_stream", side_effect=fake_prepare_rag_stream
            ), patch("app.api.routes.chat.astream_rag_answer", fake_stream), patch(
                "app.api.routes.chat.create_conversation_service", return_value=_FakeService()
            ):
                response = client.post(
                    "/chat/stream",
                    json={
                        "question": "Hướng dẫn thao tác chức năng hiện tại",
                        "session_id": session_id,
                        "ui_context": {
                            "portal": "hr",
                            "route": route,
                            "page_title": title,
                            "page_purpose": f"Mục đích trang {title}",
                            "available_features": ["Tính năng A"],
                            "related_pages": [{"route": "/hr", "title": "Tổng quan nhân sự"}],
                        },
                    },
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(captured_turn_question["value"], "Hướng dẫn thao tác chức năng hiện tại")
            self.assertIsInstance(captured_prepare["ui_context"], UiPageContext)
            assert isinstance(captured_prepare["ui_context"], UiPageContext)
            self.assertEqual(captured_prepare["ui_context"].route, route)
            self.assertEqual(captured_prepare["ui_context"].page_title, title)
            frames = self._parse_frames(response)
            self.assertEqual(frames[-1][0], "done")

    def test_chat_json_and_workspace_stateless_preserve_existing_behavior_and_reject_unsafe_route(self) -> None:
        client = TestClient(self._make_app())
        captured_no_ui: dict[str, object] = {}

        def fake_answer(question, *, database, qdrant_client, session_id=None, ui_context=None):
            captured_no_ui["question"] = question
            captured_no_ui["ui_context"] = ui_context
            return {
                "answer": "Trả lời chuẩn RAG Workspace.",
                "sources": [],
                "usage": None,
            }

        with patch.object(settings, "tool_use_enabled", False), patch(
            "app.api.routes.chat.answer_question", side_effect=fake_answer
        ):
            ok_resp = client.post("/chat", json={"question": "Chính sách nghỉ phép năm?"})

        self.assertEqual(ok_resp.status_code, 200)
        self.assertIsNone(captured_no_ui["ui_context"])

        bad_resp = client.post(
            "/chat",
            json={
                "question": "Hướng dẫn",
                "ui_context": {
                    "route": "https://evil.example/phish",
                    "page_title": "Test",
                    "page_purpose": "Test",
                },
            },
        )
        self.assertEqual(bad_resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()
