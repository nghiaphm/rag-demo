"""SSE integration through the real facade, query and conversation services; offline I/O."""

import asyncio
import json
import socket
import unittest
from dataclasses import replace
from time import monotonic
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from langchain_core.messages import AIMessageChunk
from langchain_core.prompt_values import ChatPromptValue
from pymongo.errors import ExecutionTimeout, OperationFailure

from app.api.routes.chat import chat_stream, router
from app.chat.orchestrator import ChatOrchestrator
from app.shared.config import settings
from app.conversations.models import MessageStatus
from app.conversations.repository import ConversationRepositoryError, SessionConflictError
from app.conversations.service import ConversationService
from app.documents.indexes import DOCUMENTS_COLLECTION, DOCUMENT_VERSIONS_COLLECTION, INGESTION_JOBS_COLLECTION
from app.documents.queries import DocumentQueries
from app.chat.pipeline import PreparedRagStream, ProviderStreamChunk
from app.chat.query_rewriting import QueryRewriteResult, RewriteMetrics, RewriteStatus
from app.api.schemas.chat_documents import ChatRequest, Source
from app.api.streaming.sse_schema import SSETranscript
from app.api.streaming.stream_metrics import StreamMetricTracker

from test_chat_json_tools import GuardedCollection, MessageRepository, SESSION_ID
from test_chat_orchestration import CONFIG, FINAL_USAGE, SOURCES, FakeModel, call, selection
from test_document_queries import Collection, document


def frames(text):
    result = []
    for frame in text.strip().split("\n\n"):
        event, data = frame.splitlines()
        result.append({"event": event.removeprefix("event: "),
                       "data": json.loads(data.removeprefix("data: "))})
    return result


class StreamingRepository(MessageRepository):
    def __init__(self):
        super().__init__()
        self.streaming = []
        self.setup_error = None

    def mark_assistant_streaming(self, message):
        self.assert_owned()
        if self.setup_error:
            raise self.setup_error
        assert message.status == MessageStatus.STREAMING
        self.streaming.append(message)


class StreamToolIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.repository = StreamingRepository()
        self.service = ConversationService(self.repository)
        self.documents = GuardedCollection(document(index) for index in range(25))
        self.database = {
            DOCUMENTS_COLLECTION: self.documents,
            DOCUMENT_VERSIONS_COLLECTION: Collection(), INGESTION_JOBS_COLLECTION: Collection(),
        }
        self.model = FakeModel(selection(call()))
        self.model.chunks = [AIMessageChunk(content="Có 25 tài liệu.", usage_metadata=FINAL_USAGE)]
        self.rag_inputs, self.plans, self.order = [], [], []
        self.persistent = False

        async def selector_hook():
            # Accepted C05: selector/preparation precedes guard/pair setup for SSE.
            self.assertIsNone(self.repository.active)
            self.assertEqual(self.repository.pairs, [])
            self.order.append("selector")
        async def final_hook():
            self.order.append("final")
            if self.persistent:
                self.repository.assert_owned()
                self.assertEqual(len(self.repository.streaming), 1)
        self.model.selector_hook, self.model.final_hook = selector_hook, final_hook

        def compose(**kwargs):
            self.assertTrue(kwargs["tools_enabled"])
            self.assertIsInstance(kwargs["queries"], DocumentQueries)
            self.assertIs(kwargs["queries"].repository.documents, self.documents)
            orchestrator = ChatOrchestrator(
                **kwargs, llm=self.model, budget_config=CONFIG,
                history_loader=SimpleNamespace(load=lambda session: SimpleNamespace(turns=())),
                rag_prepare=self.prepare_rag,
            )
            original = orchestrator.prepare_plan
            async def prepare(*args, **options):
                plan = await original(*args, **options)
                self.plans.append(plan)
                return plan
            orchestrator.prepare_plan = prepare
            return orchestrator

        self.connect = self.start_patch(socket.socket, "connect", side_effect=AssertionError("offline only"))
        self.start_patch(settings, "tool_use_enabled", new=True)
        self.compose = self.start_patch("app.api.routes.chat.ChatOrchestrator", side_effect=compose)
        self.start_patch("app.api.routes.chat.create_conversation_service", return_value=self.service)
        self.metrics = self.start_patch("app.api.routes.chat.record_stream_metric")
        self.provider = self.start_patch("app.chat.orchestrator.get_llm", side_effect=AssertionError("fake only"))
        self.legacy = self.start_patch("app.api.routes.chat.prepare_rag_stream", side_effect=AssertionError("legacy forbidden"))
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.state.cloud_connections = SimpleNamespace(
            mongodb=SimpleNamespace(database=self.database), qdrant=SimpleNamespace(client=object()),
        )
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://offline")
        self.addAsyncCleanup(self.client.aclose)

    def start_patch(self, target, attribute=None, **kwargs):
        item = patch(target, **kwargs) if attribute is None else patch.object(target, attribute, **kwargs)
        result = item.start()
        self.addCleanup(item.stop)
        return result

    async def asyncTearDown(self):
        self.connect.assert_not_called()
        self.provider.assert_not_called()

    async def prepare_rag(self, question, **dependencies):
        self.rag_inputs.append((question, dependencies))
        return PreparedRagStream(prompt_value=ChatPromptValue(messages=[]), sources=SOURCES,
                                 active_version_ids=(SOURCES[0]["version_id"],))

    def payload(self, persistent):
        self.persistent = persistent
        self.documents.guard = self.repository if persistent else None
        return {"question": "Question", **({"session_id": SESSION_ID} if persistent else {})}

    async def post(self, persistent=False):
        return await self.client.post("/chat/stream", json=self.payload(persistent))

    async def response_iterator(self, persistent=True):
        request = SimpleNamespace(app=self.app)
        return await chat_stream(ChatRequest(**self.payload(persistent)), request)

    def transcript(self, response, terminal="done"):
        self.assertEqual(response.status_code, 200, response.text)
        events = frames(response.text)
        SSETranscript.model_validate({"events": events})
        names = [item["event"] for item in events]
        self.assertEqual(names[:2], ["start", "metadata"])
        self.assertEqual(names[-1], terminal)
        self.assertEqual(sum(name in {"done", "error"} for name in names), 1)
        self.assertTrue(set(names) <= {"start", "metadata", "delta", "done", "error"})
        self.assertNotIn("DRAFT", response.text)
        self.assertNotIn('"tool_calls"', response.text)
        self.assertNotIn('"envelope"', response.text)
        return events

    def assert_pair(self, events, status=MessageStatus.COMPLETED):
        self.assertEqual(len(self.repository.pairs), 1)
        self.assertEqual(len(self.repository.streaming), 1)
        self.assertEqual(len(self.repository.finalize_attempts), 1)
        self.assertEqual(len(self.repository.releases), 1)
        user, assistant = self.repository.pairs[0]
        start = events[0]["data"]
        self.assertEqual(start["request_id"], user.request_id)
        self.assertEqual(start["user_message_id"], user.message_id)
        self.assertEqual(start["assistant_message_id"], assistant.message_id)
        self.assertEqual(self.repository.finalized[-1].status, status)
        self.assertIsNone(self.repository.active)

    async def test_count_stream_has_only_final_text_and_aggregate_usage_without_qdrant(self):
        self.app.state.cloud_connections.qdrant.client = None
        events = self.transcript(await self.post())
        self.assertEqual(events[1]["data"]["sources"], [])
        self.assertEqual(events[2]["data"]["content"], "Có 25 tài liệu.")
        self.assertEqual(events[-1]["data"]["usage"], {
            "input_tokens": 9, "output_tokens": 4, "total_tokens": 13,
        })
        self.assertEqual(len(self.model.selector_inputs), 1)
        self.assertEqual(len(self.model.final_inputs), 1)
        self.assertEqual(len(self.documents.count_calls), 1)
        self.assertEqual(self.rag_inputs, [])
        self.assertEqual(self.repository.pairs, [])
        metric = self.metrics.call_args.args[0]
        self.assertEqual(metric.delta_count, 1)
        self.assertIsNotNone(metric.first_content_ms)

    async def test_persistent_count_keeps_ids_one_pair_guard_and_final_usage(self):
        events = self.transcript(await self.post(True))
        self.assert_pair(events)
        saved = self.repository.finalized[0]
        self.assertEqual(saved.content, "Có 25 tài liệu.")
        self.assertEqual(saved.citations, [])
        self.assertEqual(saved.usage.model_dump(), events[-1]["data"]["usage"])
        self.assertEqual(self.order, ["selector", "final"])

    async def test_tools_start_only_after_durable_setup_and_metadata(self):
        response = await self.response_iterator()
        self.assertEqual(len(self.repository.streaming), 1)
        self.assertEqual(self.documents.count_calls, [])
        iterator = response.body_iterator
        await anext(iterator)  # start
        await anext(iterator)  # metadata
        self.assertEqual(self.documents.count_calls, [])
        self.assertEqual(self.model.final_inputs, [])
        await anext(iterator)  # final content
        self.assertEqual(len(self.documents.count_calls), 1)
        await iterator.aclose()
        self.assertEqual(self.repository.finalized[-1].status, MessageStatus.PARTIAL)
        self.assertIsNone(self.repository.active)

    async def test_list_discloses_incomplete_page_and_never_auto_paginates(self):
        self.model.selection = selection(call("list_documents", {"limit": 20}))
        self.model.chunks = [AIMessageChunk(content="Danh sách tài liệu.", usage_metadata=FINAL_USAGE)]
        events = self.transcript(await self.post(True))
        self.assert_pair(events)
        text = "".join(e["data"]["content"] for e in events if e["event"] == "delta")
        self.assertIn("chưa đầy đủ", text)
        self.assertEqual(events[1]["data"]["sources"], [])
        tool_message = next(m for m in self.model.final_inputs[0][0] if m.type == "tool")
        data = json.loads(tool_message.content)["data"]
        self.assertEqual(data["returned_count"], 20)
        self.assertTrue(data["has_more"])
        self.assertEqual(data["next_offset"], 20)
        self.assertEqual(len(self.documents.find_calls), 1)
        self.assertNotIn(tool_message.content, text)

    async def test_no_tool_rag_keeps_ordered_sources_scope_citations_and_usage(self):
        self.model.selection = selection()
        self.model.chunks = [AIMessageChunk(content="RAG answer [1]", usage_metadata=FINAL_USAGE)]
        events = self.transcript(await self.post(True))
        self.assert_pair(events)
        self.assertEqual(events[1]["data"]["sources"], [Source(**s).model_dump(mode="json") for s in SOURCES])
        self.assertEqual(self.plans[0].sources, SOURCES)
        self.assertEqual(self.rag_inputs[0][1]["session_id"], SESSION_ID)
        self.assertIs(self.rag_inputs[0][1]["database"], self.database)
        self.assertEqual(self.documents.count_calls, [])
        self.assertEqual(self.documents.find_calls, [])
        self.assertEqual(str(self.repository.finalized[0].citations[0].chunk_id), SOURCES[0]["chunk_id"])
        self.assertEqual(events[-1]["data"]["usage"]["total_tokens"], 13)

    async def test_invalid_or_unknown_tool_fails_before_headers_and_pair(self):
        for tool in (call("unknown"), call(arguments={"limit": 2})):
            with self.subTest(tool=tool):
                self.model.selection = selection(tool)
                response = await self.post(True)
                self.assertEqual(response.status_code, 502)
                self.assertNotIn("text/event-stream", response.headers["content-type"])
                self.assertEqual(self.repository.pairs, [])
                self.assertEqual(self.documents.count_calls, [])
                self.assertEqual(self.model.final_inputs, [])

    async def test_selector_failure_is_safe_preheader_502_without_fallback(self):
        self.model.selector_error = ValueError("SENSITIVE")
        response = await self.post()
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("SENSITIVE", response.text)
        self.assertEqual(response.json()["status"], "FAILED")
        self.assertEqual(self.repository.pairs, [])
        self.assertEqual(self.model.final_inputs, [])
        self.legacy.assert_not_called()

    async def test_guard_rejection_occurs_after_preparation_but_before_tools(self):
        self.repository.begin_error = SessionConflictError("busy")
        response = await self.post(True)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(self.model.selector_inputs), 1)
        self.assertEqual(self.documents.count_calls, [])
        self.assertEqual(self.model.final_inputs, [])

    async def test_streaming_setup_failure_prevents_tools_and_final_calls(self):
        self.repository.setup_error = ConversationRepositoryError("setup")
        response = await self.post(True)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.documents.count_calls, [])
        self.assertEqual(self.model.final_inputs, [])
        self.assertIsNone(self.repository.active)

    async def test_query_failure_or_timeout_is_postheader_error_without_final_or_fallback(self):
        for error in (OperationFailure("SENSITIVE"), ExecutionTimeout("timeout")):
            with self.subTest(error=type(error).__name__):
                self.repository = StreamingRepository()
                self.service.repository = self.repository
                self.documents.count_error = error
                events = self.transcript(await self.post(True), "error")
                self.assert_pair(events, MessageStatus.FAILED)
                self.assertEqual(events[-1]["data"]["status"], "FAILED")
                self.assertEqual(self.model.final_inputs, [])
                self.assertEqual(self.rag_inputs, [])
                # Only selector ran; no missing final invocation to account for.
                self.assertEqual(events[-1]["data"]["usage"]["total_tokens"], 3)
                self.assertEqual(self.repository.finalized[0].usage.total_tokens, 3)

    async def test_final_failure_before_text_is_failed_not_tool_success(self):
        self.model.final_error = ValueError("SENSITIVE")
        events = self.transcript(await self.post(True), "error")
        self.assert_pair(events, MessageStatus.FAILED)
        self.assertEqual(len(self.documents.count_calls), 1)
        self.assertEqual(events[-1]["data"]["error"]["code"], "RAG_STREAM_ERROR")
        self.assertIsNone(events[-1]["data"]["usage"])

    async def test_final_failure_after_text_persists_partial(self):
        async def fail_stream(messages, **options):
            self.model.final_inputs.append((messages, options))
            yield AIMessageChunk(content="Partial answer")
            raise ValueError("SENSITIVE")
        self.model.astream = fail_stream
        events = self.transcript(await self.post(True), "error")
        self.assert_pair(events, MessageStatus.PARTIAL)
        self.assertEqual(self.repository.finalized[0].content, "Partial answer")
        self.assertIsNone(events[-1]["data"]["usage"])

    async def test_final_empty_answer_is_failed(self):
        self.model.chunks = []
        events = self.transcript(await self.post(True), "error")
        self.assert_pair(events, MessageStatus.FAILED)
        self.assertEqual(events[-1]["data"]["error"]["code"], "RAG_STREAM_EMPTY")

    async def test_empty_final_with_actual_usage_keeps_aggregate_on_error(self):
        self.model.chunks = [AIMessageChunk(content="", usage_metadata=FINAL_USAGE)]
        events = self.transcript(await self.post(True), "error")
        self.assert_pair(events, MessageStatus.FAILED)
        self.assertEqual(events[-1]["data"]["usage"]["total_tokens"], 13)
        self.assertEqual(self.repository.finalized[0].usage.total_tokens, 13)

    async def test_persistence_failure_has_error_terminal_and_releases_guard(self):
        self.repository.finalize_error = ConversationRepositoryError("SENSITIVE")
        events = self.transcript(await self.post(True), "error")
        self.assertEqual(events[-1]["data"]["error"]["code"], "STREAM_PERSISTENCE_ERROR")
        self.assertEqual(len(self.repository.finalize_attempts), 1)
        self.assertIsNone(self.repository.active)

    async def test_release_failure_after_commit_has_error_terminal(self):
        self.repository.release_error = ConversationRepositoryError("SENSITIVE")
        events = self.transcript(await self.post(True), "error")
        self.assertEqual(events[-1]["data"]["error"]["code"], "STREAM_PERSISTENCE_ERROR")
        self.assertEqual(self.repository.finalized[0].status, MessageStatus.COMPLETED)
        self.assertEqual(len(self.repository.releases), 1)

    async def test_cumulative_snapshots_are_counted_once(self):
        self.model.chunks = [AIMessageChunk(content="One", usage_metadata=FINAL_USAGE),
                             AIMessageChunk(content=" two", usage_metadata=FINAL_USAGE)]
        events = self.transcript(await self.post(True))
        self.assertEqual(events[-1]["data"]["usage"]["total_tokens"], 13)
        self.assertEqual(self.repository.finalized[0].usage.total_tokens, 13)

    async def test_missing_selector_or_final_actual_usage_stays_null(self):
        for missing in ("selector", "final"):
            with self.subTest(missing=missing):
                self.model.selection = selection(call(), usage=None if missing == "selector" else {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3})
                self.model.chunks = [AIMessageChunk(content="Answer", usage_metadata=None if missing == "final" else FINAL_USAGE)]
                events = self.transcript(await self.post())
                self.assertIsNone(events[-1]["data"]["usage"])

    async def test_rag_actual_rewrite_usage_joins_selector_and_final_once(self):
        self.model.selection = selection()
        prepare = self.prepare_rag
        async def with_rewrite(*args, **kwargs):
            prepared = await prepare(*args, **kwargs)
            return replace(prepared, rewrite=QueryRewriteResult(
                "Question", "Rewritten", True, RewriteStatus.REWRITTEN, "history",
                RewriteMetrics(1, 1.0, 4, 1, 5, "provider"),
            ))
        self.prepare_rag = with_rewrite
        events = self.transcript(await self.post(True))
        self.assertEqual(events[-1]["data"]["usage"], {
            "input_tokens": 13, "output_tokens": 5, "total_tokens": 18,
        })
        self.assertEqual(self.repository.finalized[0].usage.total_tokens, 18)

    async def test_metrics_include_selector_and_tool_time_but_first_content_is_final_text(self):
        now = [0.0]
        selector, final = self.model.selector_hook, self.model.final_hook
        async def timed_selector():
            await selector()
            now[0] += 2
        async def timed_final():
            await final()
            now[0] += 7
        self.model.selector_hook, self.model.final_hook = timed_selector, timed_final
        count = self.documents.count_documents
        def timed_count(*args, **kwargs):
            now[0] += 3
            return count(*args, **kwargs)
        self.documents.count_documents = timed_count
        with patch("app.api.routes.chat.StreamMetricTracker", side_effect=lambda: StreamMetricTracker(clock=lambda: now[0])):
            self.transcript(await self.post())
        metric = self.metrics.call_args.args[0]
        self.assertEqual(metric.first_event_ms, 2000)
        self.assertEqual(metric.first_content_ms, 12000)
        self.assertEqual(metric.total_latency_ms, 12000)
        self.metrics.assert_called_once()

    async def test_disconnect_after_metadata_does_not_start_tools_or_final(self):
        response = await self.response_iterator()
        iterator = response.body_iterator
        await anext(iterator)
        await anext(iterator)
        await iterator.aclose()
        self.assertEqual(self.documents.count_calls, [])
        self.assertEqual(self.model.final_inputs, [])
        self.assertEqual(self.repository.finalized[0].status, MessageStatus.FAILED)
        self.assertEqual(self.repository.finalized[0].error_code, "RAG_STREAM_CANCELLED")
        self.assertIsNone(self.repository.active)

    async def test_cancellation_during_final_propagates_and_stops_calls(self):
        entered = asyncio.Event()
        async def wait_final():
            entered.set()
            await asyncio.Event().wait()
        self.model.final_hook = wait_final
        response = await self.response_iterator()
        iterator = response.body_iterator
        await anext(iterator)
        await anext(iterator)
        task = asyncio.create_task(anext(iterator))
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(len(self.documents.count_calls), 1)
        self.assertEqual(len(self.model.final_inputs), 1)
        self.assertEqual(self.model.stream_closed, 1)
        self.assertEqual(self.repository.finalized[0].error_code, "RAG_STREAM_CANCELLED")
        self.assertIsNone(self.repository.active)

    async def test_cancellation_during_tool_stage_never_starts_final_or_fallback(self):
        entered = asyncio.Event()
        async def wait_tools(executor, calls, **options):
            self.repository.assert_owned()
            entered.set()
            await asyncio.Event().wait()
        with patch("app.tool_use.executor.ToolExecutor.execute", new=wait_tools):
            response = await self.response_iterator()
            iterator = response.body_iterator
            await anext(iterator)
            await anext(iterator)
            task = asyncio.create_task(anext(iterator))
            await asyncio.wait_for(entered.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(self.model.final_inputs, [])
        self.assertEqual(self.documents.count_calls, [])
        self.assertEqual(self.rag_inputs, [])
        self.assertEqual(self.repository.finalized[0].error_code, "RAG_STREAM_CANCELLED")
        self.assertIsNone(self.repository.active)

    async def test_preparation_deadline_is_not_reset_when_iterator_starts(self):
        response = await self.response_iterator()
        self.plans[0].deadline = monotonic() - 1
        text = "".join([frame async for frame in response.body_iterator])
        events = frames(text)
        SSETranscript.model_validate({"events": events})
        self.assertEqual(events[-1]["data"]["error"]["code"], "RAG_STREAM_TIMEOUT")
        self.assertEqual(events[-1]["data"]["usage"]["total_tokens"], 3)
        self.assertEqual(self.documents.count_calls, [])
        self.assertEqual(self.model.final_inputs, [])
        self.assertIsNone(self.repository.active)

    async def test_disabled_path_uses_legacy_stream_without_facade_or_extra_invocations(self):
        settings.tool_use_enabled = False
        prepared = PreparedRagStream(prompt_value="unused", sources=SOURCES)
        async def legacy_stream(plan):
            self.assertIs(plan, prepared)
            yield ProviderStreamChunk("Legacy SSE", FINAL_USAGE)
        with patch("app.api.routes.chat.prepare_rag_stream", return_value=prepared) as prepare, \
                patch("app.api.routes.chat.astream_rag_answer", legacy_stream):
            events = self.transcript(await self.post(True))
        self.assert_pair(events)
        self.assertEqual(events[1]["data"]["sources"], [Source(**s).model_dump(mode="json") for s in SOURCES])
        self.assertEqual(events[-1]["data"]["usage"], FINAL_USAGE)
        prepare.assert_called_once()
        self.compose.assert_not_called()
        self.assertEqual(self.model.selector_inputs, [])
        self.assertEqual(self.documents.count_calls, [])
