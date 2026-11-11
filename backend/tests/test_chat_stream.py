"""P4-01 transport tests for POST /chat/stream."""

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.chat import _encode_provider_stream, router
from app.shared.config import settings
from app.conversations.models import MessageRecord, MessageRole, MessageStatus
from app.conversations.repository import ConversationRepositoryError, SessionNotFoundError
from app.conversations.service import StreamingTurn
from app.chat.pipeline import ProviderStreamChunk
from app.api.streaming.sse_schema import SSETranscript


class ChatStreamApiTests(unittest.TestCase):
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
    def sources() -> list[dict]:
        return [
            {
                "chunk_id": str(uuid4()),
                "document_id": str(uuid4()),
                "version_id": str(uuid4()),
                "file_name": "guide.md",
                "page": 1,
            }
        ]

    @staticmethod
    def frames(response) -> list[tuple[str, dict]]:
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

    def test_stateless_stream_uses_typed_sse_order_and_headers(self):
        prepared = SimpleNamespace(sources=self.sources())
        metrics = []

        async def provider_stream(_prepared):
            yield ProviderStreamChunk(content="Xin ", usage=None)
            yield ProviderStreamChunk(content=None, usage=None)
            yield ProviderStreamChunk(
                content="chào [1]",
                usage={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
            )

        with patch("app.api.routes.chat.prepare_rag_stream", return_value=prepared), patch(
            "app.api.routes.chat.astream_rag_answer", provider_stream
        ), patch("app.api.routes.chat.record_stream_metric", side_effect=metrics.append):
            response = TestClient(self.make_app()).post(
                "/chat/stream", json={"question": "Question"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        self.assertEqual(response.headers["cache-control"], "no-cache, no-transform")
        self.assertEqual(response.headers["x-accel-buffering"], "no")
        frames = self.frames(response)
        self.assertEqual(
            [event for event, _ in frames],
            ["start", "metadata", "delta", "delta", "done"],
        )
        self.assertEqual(
            [data["sequence"] for _, data in frames], list(range(1, 6))
        )
        start = frames[0][1]
        self.assertEqual(start["mode"], "STATELESS")
        self.assertIsNone(start["session_id"])
        self.assertIsNone(start["user_message_id"])
        self.assertIsNone(start["assistant_message_id"])
        self.assertEqual(frames[1][1]["sources"][0]["file_name"], "guide.md")
        self.assertEqual(frames[2][1]["content"], "Xin ")
        self.assertEqual(frames[3][1]["content"], "chào [1]")
        self.assertEqual(frames[4][1]["status"], "COMPLETED")
        self.assertEqual(frames[4][1]["usage"]["total_tokens"], 10)
        transcript = SSETranscript(
            events=[{"event": event, "data": data} for event, data in frames]
        )
        self.assertEqual(transcript.reconstructed_answer, "Xin chào [1]")
        self.assertEqual(len(metrics), 1)
        metric = metrics[0]
        self.assertEqual(metric.outcome, "COMPLETED")
        self.assertEqual(metric.mode, "STATELESS")
        self.assertEqual(metric.delta_count, 2)
        self.assertIsNotNone(metric.first_event_ms)
        self.assertIsNotNone(metric.first_content_ms)
        self.assertLessEqual(metric.first_event_ms, metric.first_content_ms)
        self.assertLessEqual(metric.first_content_ms, metric.total_latency_ms)

    def test_empty_provider_output_has_failed_terminal_and_nullable_content_metric(self):
        metrics = []

        async def provider_stream(_prepared):
            yield ProviderStreamChunk(content=None, usage=None)

        with patch(
            "app.api.routes.chat.prepare_rag_stream", return_value=SimpleNamespace(sources=[])
        ), patch("app.api.routes.chat.astream_rag_answer", provider_stream), patch(
            "app.api.routes.chat.record_stream_metric", side_effect=metrics.append
        ):
            response = TestClient(self.make_app()).post(
                "/chat/stream", json={"question": "Question"}
            )
        frames = self.frames(response)
        self.assertEqual([event for event, _ in frames], ["start", "metadata", "error"])
        self.assertEqual(frames[-1][1]["status"], "FAILED")
        self.assertEqual(frames[-1][1]["error"]["code"], "RAG_STREAM_EMPTY")
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].outcome, "RAG_STREAM_EMPTY")
        self.assertIsNone(metrics[0].first_content_ms)
        self.assertEqual(metrics[0].delta_count, 0)

    def test_session_stream_persists_lifecycle_and_returns_persistent_ids(self):
        session_id = str(uuid4())
        request_id = str(uuid4())
        user = MessageRecord(
            session_id=session_id,
            sequence=1,
            role=MessageRole.USER,
            content="Question",
            status=MessageStatus.COMPLETED,
            request_id=request_id,
        )
        assistant = MessageRecord(
            session_id=session_id,
            sequence=2,
            role=MessageRole.ASSISTANT,
            status=MessageStatus.STREAMING,
            model="provider/model",
            request_id=request_id,
        )
        turn = StreamingTurn(request_id, user, assistant)

        class Service:
            finalized = None

            def begin_streaming_turn(self, **kwargs):
                return turn

            def finalize_streaming_turn(self, received_turn, **kwargs):
                self.finalized = (received_turn, kwargs)

        service = Service()
        prepared = SimpleNamespace(sources=[])

        async def provider_stream(_prepared):
            yield ProviderStreamChunk(content="Answer", usage=None)

        with patch(
            "app.api.routes.chat.prepare_rag_stream", return_value=prepared
        ) as prepare, patch(
            "app.api.routes.chat.create_conversation_service", return_value=service
        ), patch("app.api.routes.chat.astream_rag_answer", provider_stream):
            response = TestClient(self.make_app()).post(
                "/chat/stream",
                json={"question": "Question", "session_id": session_id},
            )
        self.assertEqual(response.status_code, 200)
        frames = self.frames(response)
        self.assertEqual(frames[0][1]["mode"], "PERSISTENT")
        self.assertEqual(frames[0][1]["session_id"], session_id)
        self.assertEqual(frames[0][1]["user_message_id"], user.message_id)
        self.assertEqual(frames[0][1]["assistant_message_id"], assistant.message_id)
        self.assertEqual(service.finalized[0], turn)
        self.assertEqual(service.finalized[1]["content"], "Answer")
        self.assertIsNone(service.finalized[1]["error_code"])
        self.assertEqual(prepare.call_args.kwargs["session_id"], session_id)

    def test_stream_provider_failure_emits_partial_error_and_persists_it(self):
        session_id = str(uuid4())
        request_id = str(uuid4())
        user = MessageRecord(
            session_id=session_id,
            sequence=1,
            role=MessageRole.USER,
            content="Question",
            status=MessageStatus.COMPLETED,
            request_id=request_id,
        )
        assistant = MessageRecord(
            session_id=session_id,
            sequence=2,
            role=MessageRole.ASSISTANT,
            status=MessageStatus.STREAMING,
            model="provider/model",
            request_id=request_id,
        )
        turn = StreamingTurn(request_id, user, assistant)

        class Service:
            finalized = None

            def begin_streaming_turn(self, **kwargs):
                return turn

            def finalize_streaming_turn(self, received_turn, **kwargs):
                self.finalized = (received_turn, kwargs)

        service = Service()
        prepared = SimpleNamespace(sources=[])
        metrics = []

        async def provider_stream(_prepared):
            yield ProviderStreamChunk(content="partial", usage=None)
            raise RuntimeError("provider detail must not leak")

        with patch("app.api.routes.chat.prepare_rag_stream", return_value=prepared), patch(
            "app.api.routes.chat.create_conversation_service", return_value=service
        ), patch("app.api.routes.chat.astream_rag_answer", provider_stream), patch(
            "app.api.routes.chat.record_stream_metric", side_effect=metrics.append
        ):
            response = TestClient(self.make_app()).post(
                "/chat/stream",
                json={"question": "Question", "session_id": session_id},
            )
        self.assertEqual(response.status_code, 200)
        frames = self.frames(response)
        self.assertEqual([event for event, _ in frames], ["start", "metadata", "delta", "error"])
        self.assertEqual(frames[-1][1]["status"], "PARTIAL")
        self.assertEqual(frames[-1][1]["error"]["code"], "RAG_STREAM_ERROR")
        self.assertNotIn("provider detail", response.text)
        self.assertEqual(service.finalized[1]["content"], "partial")
        self.assertEqual(service.finalized[1]["error_code"], "RAG_STREAM_ERROR")
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].outcome, "RAG_STREAM_ERROR")
        self.assertIsNotNone(metrics[0].first_content_ms)

    def test_stream_timeout_cancels_provider_and_emits_terminal_error(self):
        prepared = SimpleNamespace(sources=[])
        provider_closed = False

        async def provider_stream(_prepared):
            nonlocal provider_closed
            try:
                await asyncio.sleep(1)
                yield ProviderStreamChunk(content="late", usage=None)
            finally:
                provider_closed = True

        with patch("app.api.routes.chat.prepare_rag_stream", return_value=prepared), patch(
            "app.api.routes.chat.astream_rag_answer", provider_stream
        ), patch.object(settings, "stream_timeout_seconds", 0.01):
            response = TestClient(self.make_app()).post(
                "/chat/stream", json={"question": "Question"}
            )
        frames = self.frames(response)
        self.assertEqual([event for event, _ in frames], ["start", "metadata", "error"])
        self.assertEqual(frames[-1][1]["status"], "FAILED")
        self.assertEqual(frames[-1][1]["error"]["code"], "RAG_STREAM_TIMEOUT")
        self.assertTrue(provider_closed)

    def test_persistence_failure_after_headers_is_terminal_sse_error(self):
        session_id = str(uuid4())
        request_id = str(uuid4())
        turn = StreamingTurn(
            request_id,
            MessageRecord(
                session_id=session_id,
                sequence=1,
                role=MessageRole.USER,
                content="Question",
                status=MessageStatus.COMPLETED,
                request_id=request_id,
            ),
            MessageRecord(
                session_id=session_id,
                sequence=2,
                role=MessageRole.ASSISTANT,
                status=MessageStatus.STREAMING,
                model="provider/model",
                request_id=request_id,
            ),
        )

        class Service:
            def begin_streaming_turn(self, **kwargs):
                return turn

            def finalize_streaming_turn(self, received_turn, **kwargs):
                raise ConversationRepositoryError("private database detail")

        async def provider_stream(_prepared):
            yield ProviderStreamChunk(content="answer", usage=None)

        with patch(
            "app.api.routes.chat.prepare_rag_stream", return_value=SimpleNamespace(sources=[])
        ), patch("app.api.routes.chat.create_conversation_service", return_value=Service()), patch(
            "app.api.routes.chat.astream_rag_answer", provider_stream
        ):
            response = TestClient(self.make_app()).post(
                "/chat/stream",
                json={"question": "Question", "session_id": session_id},
            )
        frames = self.frames(response)
        self.assertEqual([event for event, _ in frames], ["start", "metadata", "delta", "error"])
        self.assertEqual(frames[-1][1]["status"], "PARTIAL")
        self.assertEqual(frames[-1][1]["error"]["code"], "STREAM_PERSISTENCE_ERROR")
        self.assertNotIn("private database detail", response.text)

    def test_cancelled_stream_persists_terminal_state_and_stops_provider(self):
        session_id = str(uuid4())
        request_id = str(uuid4())
        turn = StreamingTurn(
            request_id,
            MessageRecord(
                session_id=session_id,
                sequence=1,
                role=MessageRole.USER,
                content="Question",
                status=MessageStatus.COMPLETED,
                request_id=request_id,
            ),
            MessageRecord(
                session_id=session_id,
                sequence=2,
                role=MessageRole.ASSISTANT,
                status=MessageStatus.STREAMING,
                model="provider/model",
                request_id=request_id,
            ),
        )

        class Service:
            finalized = None

            def finalize_streaming_turn(self, received_turn, **kwargs):
                self.finalized = (received_turn, kwargs)

        service = Service()
        started = asyncio.Event()
        closed = asyncio.Event()

        async def provider_stream(_prepared):
            try:
                started.set()
                await asyncio.Event().wait()
                yield ProviderStreamChunk(content="unreachable", usage=None)
            finally:
                closed.set()

        async def exercise():
            stream = _encode_provider_stream(
                request_id=request_id,
                prepared=SimpleNamespace(sources=[]),
                service=service,
                turn=turn,
            )
            await anext(stream)
            await anext(stream)
            pending = asyncio.create_task(anext(stream))
            await started.wait()
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending
            await stream.aclose()

        metrics = []
        with patch("app.api.routes.chat.astream_rag_answer", provider_stream), patch(
            "app.api.routes.chat.record_stream_metric", side_effect=metrics.append
        ):
            asyncio.run(exercise())
        self.assertTrue(closed.is_set())
        self.assertEqual(service.finalized[0], turn)
        self.assertEqual(service.finalized[1]["content"], "")
        self.assertEqual(service.finalized[1]["error_code"], "RAG_STREAM_CANCELLED")
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].outcome, "RAG_STREAM_CANCELLED")
        self.assertIsNone(metrics[0].first_content_ms)

    def test_disconnect_after_start_still_finalizes_persistent_turn(self):
        session_id = str(uuid4())
        request_id = str(uuid4())
        turn = StreamingTurn(
            request_id,
            MessageRecord(
                session_id=session_id,
                sequence=1,
                role=MessageRole.USER,
                content="Question",
                status=MessageStatus.COMPLETED,
                request_id=request_id,
            ),
            MessageRecord(
                session_id=session_id,
                sequence=2,
                role=MessageRole.ASSISTANT,
                status=MessageStatus.STREAMING,
                model="provider/model",
                request_id=request_id,
            ),
        )

        class Service:
            finalized = None

            def finalize_streaming_turn(self, received_turn, **kwargs):
                self.finalized = (received_turn, kwargs)

        service = Service()

        async def exercise():
            stream = _encode_provider_stream(
                request_id=request_id,
                prepared=SimpleNamespace(sources=[]),
                service=service,
                turn=turn,
            )
            first = await anext(stream)
            self.assertIn("event: start", first)
            await stream.aclose()

        asyncio.run(exercise())
        self.assertEqual(service.finalized[0], turn)
        self.assertEqual(service.finalized[1]["content"], "")
        self.assertEqual(service.finalized[1]["error_code"], "RAG_STREAM_CANCELLED")

    def test_missing_persistent_session_is_pre_header_404(self):
        class Service:
            def begin_streaming_turn(self, **kwargs):
                raise SessionNotFoundError()

        with patch(
            "app.api.routes.chat.prepare_rag_stream", return_value=SimpleNamespace(sources=[])
        ), patch("app.api.routes.chat.create_conversation_service", return_value=Service()), patch(
            "app.api.routes.chat.astream_rag_answer"
        ) as provider:
            response = TestClient(self.make_app()).post(
                "/chat/stream",
                json={"question": "Question", "session_id": str(uuid4())},
            )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(response.headers["content-type"].startswith("application/json"))
        provider.assert_not_called()

    def test_pre_header_generation_error_uses_safe_json_failure_envelope(self):
        metrics = []
        with patch(
            "app.api.routes.chat.prepare_rag_stream",
            side_effect=RuntimeError("private provider detail"),
        ), patch("app.api.routes.chat.record_stream_metric", side_effect=metrics.append):
            response = TestClient(self.make_app()).post(
                "/chat/stream", json={"question": "Question"}
            )
        self.assertEqual(response.status_code, 502)
        self.assertTrue(response.headers["content-type"].startswith("application/json"))
        body = response.json()
        self.assertEqual(body["status"], "FAILED")
        self.assertIsNone(body["answer"])
        self.assertEqual(body["error"]["code"], "RAG_PIPELINE_ERROR")
        self.assertNotIn("private provider detail", response.text)
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].outcome, "HTTP_502")
        self.assertIsNone(metrics[0].first_event_ms)
        self.assertIsNone(metrics[0].first_content_ms)

    def test_metrics_sink_failure_never_breaks_successful_stream(self):
        async def provider_stream(_prepared):
            yield ProviderStreamChunk(content="answer", usage=None)

        with patch(
            "app.api.routes.chat.prepare_rag_stream", return_value=SimpleNamespace(sources=[])
        ), patch("app.api.routes.chat.astream_rag_answer", provider_stream), patch(
            "app.api.routes.chat.record_stream_metric",
            side_effect=RuntimeError("metrics backend unavailable"),
        ):
            response = TestClient(self.make_app()).post(
                "/chat/stream", json={"question": "Question"}
            )
        self.assertEqual(response.status_code, 200)
        frames = self.frames(response)
        self.assertEqual([event for event, _ in frames], ["start", "metadata", "delta", "done"])
        self.assertEqual(frames[-1][1]["status"], "COMPLETED")

    def test_missing_cloud_dependency_is_pre_header_503(self):
        response = TestClient(self.make_app(database=None)).post(
            "/chat/stream", json={"question": "Question"}
        )
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
