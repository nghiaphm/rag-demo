"""JSON integration with real orchestration/query/persistence services and fake I/O."""

import asyncio
import json
import os
import socket
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import httpx
from fastapi import FastAPI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompt_values import ChatPromptValue
from pydantic import ValidationError
from pymongo.errors import ExecutionTimeout, OperationFailure

from app.api.routes.chat import router
from app.chat.orchestrator import ChatOrchestrator
from app.shared.config import Settings, settings
from app.conversations.models import MessageRecord, MessageRole, MessageStatus
from app.conversations.repository import (
    ConversationRepositoryError,
    SessionConflictError,
    SessionDeletedError,
    SessionNotFoundError,
)
from app.conversations.service import ConversationService
from app.documents.indexes import DOCUMENTS_COLLECTION, DOCUMENT_VERSIONS_COLLECTION, INGESTION_JOBS_COLLECTION
from app.documents.queries import DocumentQueries
from app.documents.repository import MongoDocumentRepository
from app.chat.pipeline import PreparedRagStream, ProviderStreamChunk
from app.api.schemas.chat_documents import ChatRequest, ChatResponse
from app.api.streaming.sse_schema import SSETranscript

# Reuse the accepted rounds' deterministic native-model and collection fixtures.
from tests.unit.test_chat_orchestration import CONFIG, FINAL_USAGE, SOURCES, FakeModel, call, selection
from tests.unit.test_document_queries import Collection, document

SESSION_ID = str(UUID(int=500))
LEGACY_RESULT = {
    "answer": "Legacy answer [1]", "sources": SOURCES,
    "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
}


class MessageRepository:
    """Record the production service's writes and enforce owned generation order."""

    def __init__(self):
        self.active = None
        self.pairs = []
        self.finalized = []
        self.finalize_attempts = []
        self.releases = []
        self.begin_error = self.finalize_error = self.release_error = None
        self.begin_thread = None

    def assert_owned(self):
        assert self.active is not None
        assert len(self.pairs) == 1
        user, pending = self.pairs[0]
        assert user.request_id == pending.request_id == self.active
        assert user.status == MessageStatus.COMPLETED
        assert pending.status == MessageStatus.PENDING

    def begin_generation(self, session_id, request_id):
        if self.begin_error:
            raise self.begin_error
        assert self.active is None
        self.active = request_id
        self.begin_thread = threading.get_ident()
        return 1, 2

    def create_message_pair(self, user, assistant):
        assert self.active == user.request_id == assistant.request_id
        assert isinstance(user, MessageRecord) and isinstance(assistant, MessageRecord)
        self.pairs.append((user, assistant))

    def finalize_assistant_message(self, message):
        self.assert_owned()
        self.finalize_attempts.append(message)
        if self.finalize_error:
            raise self.finalize_error
        self.finalized.append(message)
        return message

    def release_generation(self, session_id, request_id):
        self.releases.append((session_id, request_id))
        assert self.active == request_id
        if self.release_error:
            raise self.release_error
        self.active = None


class GuardedCollection(Collection):
    def __init__(self, values):
        super().__init__(values)
        self.guard = None

    def count_documents(self, query, **options):
        if self.guard:
            self.guard.assert_owned()
        return super().count_documents(query, **options)

    def find(self, query):
        if self.guard:
            self.guard.assert_owned()
        return super().find(query)


class JsonToolIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        network = patch.object(socket.socket, "connect", side_effect=AssertionError("offline only"))
        self.connect = network.start()
        self.addCleanup(network.stop)
        gate = patch.object(settings, "tool_use_enabled", False)
        gate.start()
        self.addCleanup(gate.stop)
        self.documents = GuardedCollection(document(index) for index in range(6))
        self.versions, self.jobs = Collection(), Collection()
        self.database = {
            DOCUMENTS_COLLECTION: self.documents,
            DOCUMENT_VERSIONS_COLLECTION: self.versions,
            INGESTION_JOBS_COLLECTION: self.jobs,
        }
        self.qdrant = object()
        self.repository = MessageRepository()
        self.service = ConversationService(self.repository)
        self.model = FakeModel(selection(call()))
        self.model.final = AIMessage(content="Có 6 tài liệu.", usage_metadata=FINAL_USAGE)
        self.loop = asyncio.get_running_loop()
        self.loop_ids, self.history_inputs, self.rag_inputs, self.compositions = [], [], [], []
        self.persistent = False

        async def checkpoint():
            self.loop_ids.append(id(asyncio.get_running_loop()))
            if self.persistent:
                self.repository.assert_owned()
        self.model.selector_hook = self.model.final_hook = checkpoint

        def load_history(session_id):
            self.repository.assert_owned()
            self.history_inputs.append(session_id)
            return SimpleNamespace(turns=())
        self.history_loader = SimpleNamespace(load=load_history)

        def compose(**kwargs):
            self.assertEqual(set(kwargs), {"queries", "tools_enabled"})
            self.assertTrue(kwargs["tools_enabled"])
            self.assertIsInstance(kwargs["queries"], DocumentQueries)
            self.assertIsInstance(kwargs["queries"].repository, MongoDocumentRepository)
            self.assertIs(kwargs["queries"].repository.documents, self.documents)
            if self.persistent:
                self.repository.assert_owned()
            self.compositions.append(kwargs)
            return ChatOrchestrator(
                **kwargs, llm=self.model, history_loader=self.history_loader,
                budget_config=CONFIG, rag_prepare=self.prepare_rag,
            )

        composition = patch("app.api.routes.chat.ChatOrchestrator", side_effect=compose)
        self.compose = composition.start()
        self.addCleanup(composition.stop)
        legacy = patch("app.api.routes.chat.answer_question", return_value=LEGACY_RESULT)
        self.legacy = legacy.start()
        self.addCleanup(legacy.stop)
        service = patch("app.api.routes.chat.create_conversation_service", return_value=self.service)
        self.service_factory = service.start()
        self.addCleanup(service.stop)
        provider = patch("app.chat.orchestrator.get_llm", side_effect=AssertionError("fake model required"))
        self.real_provider = provider.start()
        self.addCleanup(provider.stop)

        self.app = FastAPI()
        self.app.include_router(router)
        self.app.state.cloud_connections = SimpleNamespace(
            mongodb=SimpleNamespace(database=self.database),
            qdrant=SimpleNamespace(client=self.qdrant),
        )
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://offline")
        self.addAsyncCleanup(self.client.aclose)

    async def asyncTearDown(self):
        self.connect.assert_not_called()
        self.real_provider.assert_not_called()

    async def prepare_rag(self, question, **dependencies):
        self.rag_inputs.append((question, dependencies))
        if dependencies["qdrant_client"] is None:
            raise ValueError("SENSITIVE unavailable retrieval dependency")
        return PreparedRagStream(
            prompt_value=ChatPromptValue(messages=[SystemMessage(content="RAG"), HumanMessage(content=question)]),
            sources=SOURCES,
            active_version_ids=(SOURCES[0]["version_id"],),
        )

    async def post(self, *, persistent=False, question="Question", **extra):
        self.persistent = persistent
        self.documents.guard = self.repository if persistent else None
        payload = {"question": question, **extra}
        if persistent:
            payload["session_id"] = SESSION_ID
        return await self.client.post("/chat", json=payload)

    def enable(self):
        settings.tool_use_enabled = True

    def assert_failure(self, response, *, persistent=False):
        self.assertEqual(response.status_code, 502, response.text)
        body = response.json()
        ChatResponse.model_validate(body)
        self.assertEqual(body["status"], "FAILED")
        self.assertEqual(body["error"]["code"], "RAG_PIPELINE_ERROR")
        self.assertIsNone(body["answer"])
        self.assertIsNone(body["usage"])
        self.assertEqual(body["sources"], [])
        self.assertEqual(body["citations"], [])
        self.assertNotIn("SENSITIVE", response.text)
        if persistent:
            user, pending = self.repository.pairs[0]
            self.assertEqual(body["session_id"], SESSION_ID)
            self.assertEqual(body["request_id"], user.request_id)
            self.assertEqual(body["user_message_id"], user.message_id)
            self.assertEqual(body["assistant_message_id"], pending.message_id)
            self.assertEqual(self.repository.finalized[-1].status, MessageStatus.FAILED)
            self.assertEqual(self.repository.finalized[-1].error_code, "RAG_PIPELINE_ERROR")
            self.assertIsNone(self.repository.active)
        return body

    async def test_gate_disabled_stateless_is_exact_legacy_path_without_selector_or_tools(self):
        response = await self.post()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["answer"], LEGACY_RESULT["answer"])
        self.assertEqual(body["usage"], LEGACY_RESULT["usage"])
        self.assertEqual(body["metadata"]["mode"], "STATELESS")
        self.legacy.assert_called_once_with("Question", database=self.database, qdrant_client=self.qdrant)
        self.compose.assert_not_called()
        self.service_factory.assert_not_called()
        self.assertEqual(self.model.selector_inputs, [])
        self.assertEqual(self.model.final_inputs, [])
        self.assertEqual(self.documents.count_calls, [])
        self.assertEqual(self.documents.find_calls, [])

    async def test_gate_disabled_persistent_still_uses_legacy_callback_and_one_pair(self):
        response = await self.post(persistent=True)
        self.assertEqual(response.status_code, 200)
        self.legacy.assert_called_once_with("Question", database=self.database, qdrant_client=self.qdrant,
                                            session_id=SESSION_ID)
        self.compose.assert_not_called()
        self.assertEqual(len(self.repository.pairs), 1)
        self.assertEqual(len(self.repository.finalized), 1)
        self.assertEqual(response.json()["usage"], LEGACY_RESULT["usage"])
        self.assertIsNone(self.repository.active)

    async def test_client_payload_cannot_enable_server_side_gate(self):
        response = await self.post(tool_use_enabled=True)
        self.assertEqual(response.status_code, 200)
        self.legacy.assert_called_once()
        self.compose.assert_not_called()
        self.assertNotIn("tool_use_enabled", ChatRequest.model_fields)

    async def test_legacy_readiness_and_error_envelopes_are_unchanged(self):
        self.app.state.cloud_connections.qdrant.client = None
        response = await self.post()
        self.assertEqual(response.status_code, 503)
        self.legacy.assert_not_called()
        self.app.state.cloud_connections.qdrant.client = self.qdrant
        self.legacy.side_effect = RuntimeError("SENSITIVE_PROVIDER")
        self.assert_failure(await self.post())
        self.compose.assert_not_called()

    async def test_stateless_count_uses_real_document_query_and_does_not_persist(self):
        self.enable()
        response = await self.post(question="How many documents?")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["answer"], "Có 6 tài liệu.")
        self.assertEqual(body["sources"], [])
        self.assertEqual(body["citations"], [])
        self.assertIsNone(body["session_id"])
        self.assertIsNone(body["user_message_id"])
        self.assertIsNone(body["assistant_message_id"])
        self.assertEqual(body["usage"], {"input_tokens": 9, "output_tokens": 4, "total_tokens": 13})
        tool = next(message for message in self.model.final_inputs[0][0] if message.type == "tool")
        self.assertEqual(json.loads(tool.content)["data"]["count"], 6)
        self.assertEqual(len(self.documents.count_calls), 1)
        self.assertEqual(self.documents.find_calls, [])
        self.service_factory.assert_not_called()
        self.assertEqual(self.repository.pairs, [])
        self.assertEqual(self.repository.finalized, [])
        self.legacy.assert_not_called()

    async def test_metadata_tool_does_not_require_a_qdrant_client_or_do_retrieval(self):
        self.enable()
        self.app.state.cloud_connections.qdrant.client = None
        response = await self.post(question="Count")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.rag_inputs, [])
        self.assertEqual(len(self.documents.count_calls), 1)

    async def test_stateless_list_preserves_page_metadata_and_declares_incompleteness(self):
        self.enable()
        self.documents.values = [document(index) for index in range(25)]
        self.model.selection = selection(call("list_documents", {"limit": 20}))
        self.model.final = AIMessage(content="Các tài liệu trong trang được trả về.", usage_metadata=FINAL_USAGE)
        response = await self.post(question="List documents")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIn("Danh sách này chưa đầy đủ", body["answer"])
        self.assertIn("next_offset=20", body["answer"])
        self.assertNotIn("tất cả", body["answer"])
        self.assertEqual(body["sources"], [])
        self.assertEqual(body["citations"], [])
        tool = next(message for message in self.model.final_inputs[0][0] if message.type == "tool")
        data = json.loads(tool.content)["data"]
        self.assertEqual(data["returned_count"], 20)
        self.assertEqual(data["next_offset"], 20)
        self.assertTrue(data["has_more"])
        self.assertEqual(len(self.documents.find_calls), 1)
        self.service_factory.assert_not_called()

    async def test_persistent_count_keeps_guard_pair_callback_loop_and_usage_ownership(self):
        self.enable()
        response = await self.post(persistent=True, question="Count documents")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(self.repository.pairs), 1)
        self.assertEqual(len(self.repository.finalized), 1)
        user, pending = self.repository.pairs[0]
        completed = self.repository.finalized[0]
        self.assertEqual((user.sequence, pending.sequence), (1, 2))
        self.assertEqual((user.role, pending.role), (MessageRole.USER, MessageRole.ASSISTANT))
        self.assertEqual(completed.status, MessageStatus.COMPLETED)
        self.assertEqual(completed.content, body["answer"])
        self.assertEqual(completed.usage.model_dump(), body["usage"])
        self.assertEqual(body["usage"]["total_tokens"], 13)
        self.assertEqual(completed.citations, [])
        self.assertEqual(body["user_message_id"], user.message_id)
        self.assertEqual(body["assistant_message_id"], pending.message_id)
        self.assertEqual(body["request_id"], user.request_id)
        self.assertEqual(self.history_inputs, [SESSION_ID])
        self.assertEqual(self.loop_ids, [id(self.loop), id(self.loop)])
        self.assertNotEqual(self.repository.begin_thread, threading.get_ident())
        self.assertEqual(len(self.repository.releases), 1)
        self.assertIsNone(self.repository.active)
        self.assertNotIn("tool_calls", completed.model_dump())
        self.assertNotIn("sources", completed.model_dump())  # Existing storage holds citations, not ordered sources.

    async def test_persistent_list_creates_no_pair_for_selector_or_native_tool_messages(self):
        self.enable()
        self.documents.values = [document(index) for index in range(25)]
        self.model.selection = selection(call("list_documents"))
        self.model.final = AIMessage(content="Trang tài liệu.", usage_metadata=FINAL_USAGE)
        response = await self.post(persistent=True, question="List")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.repository.pairs), 1)
        self.assertEqual(len(self.repository.finalized), 1)
        self.assertIn("Danh sách này chưa đầy đủ", response.json()["answer"])
        self.assertEqual({self.repository.pairs[0][0].role, self.repository.finalized[0].role},
                         {MessageRole.USER, MessageRole.ASSISTANT})
        self.assertEqual(self.repository.finalized[0].content, response.json()["answer"])
        self.assertEqual(len(self.documents.find_calls), 1)
        self.assertIsNone(self.repository.active)

    async def test_persistent_guard_and_session_rejections_happen_before_selector_or_queries(self):
        self.enable()
        for error, status in ((SessionNotFoundError(), 404), (SessionDeletedError(), 410),
                              (SessionConflictError(), 409), (ConversationRepositoryError(), 503)):
            with self.subTest(status=status):
                self.repository.begin_error = error
                response = await self.post(persistent=True)
                self.assertEqual(response.status_code, status)
        self.assertEqual(self.repository.pairs, [])
        self.compose.assert_not_called()
        self.assertEqual(self.model.selector_inputs, [])
        self.assertEqual(self.documents.count_calls, [])

    async def test_unknown_tool_and_invalid_arguments_use_existing_failed_envelope(self):
        self.enable()
        for response in (selection(call("analyze_document")), selection(call(arguments={"include_deleted": 1}))):
            self.model.selection = response
            self.assert_failure(await self.post())
        self.assertEqual(self.documents.count_calls, [])
        self.assertEqual(self.documents.find_calls, [])
        self.assertEqual(self.model.final_inputs, [])
        self.assertEqual(self.rag_inputs, [])

    async def test_persistent_unknown_tool_is_failed_with_durable_ids_not_a_new_error_schema(self):
        self.enable()
        self.model.selection = selection(call("analyze_document"))
        self.assert_failure(await self.post(persistent=True), persistent=True)
        self.assertEqual(len(self.repository.pairs), 1)
        self.assertEqual(self.documents.count_calls, [])

    async def test_query_failure_and_timeout_do_not_become_empty_success_or_rag_fallback(self):
        self.enable()
        for error in (OperationFailure("SENSITIVE_MONGODB", code=123), ExecutionTimeout("SENSITIVE", code=50)):
            self.documents.count_error = error
            self.assert_failure(await self.post())
        self.assertEqual(len(self.documents.count_calls), 2)
        self.assertEqual(self.model.final_inputs, [])
        self.assertEqual(self.rag_inputs, [])

    async def test_persistent_query_failure_finalizes_failed_and_releases_guard(self):
        self.enable()
        self.documents.count_error = OperationFailure("SENSITIVE_DB", code=123)
        self.assert_failure(await self.post(persistent=True), persistent=True)
        self.assertEqual(self.model.final_inputs, [])
        self.assertEqual(len(self.repository.releases), 1)

    async def test_final_model_failure_does_not_turn_successful_tool_query_into_chat_success(self):
        self.enable()
        self.model.final_error = RuntimeError("SENSITIVE_GROQ")
        self.assert_failure(await self.post())
        self.assertEqual(len(self.documents.count_calls), 1)
        self.assertEqual(len(self.model.final_inputs), 1)
        self.assertEqual(self.rag_inputs, [])

    async def test_persistent_final_model_failure_keeps_existing_generation_failure_state(self):
        self.enable()
        self.model.final_error = RuntimeError("SENSITIVE_GROQ")
        self.assert_failure(await self.post(persistent=True), persistent=True)
        self.assertEqual(len(self.documents.count_calls), 1)
        self.assertEqual(self.repository.finalized[0].content, "")

    async def test_selector_failure_is_safe_and_never_falls_back_to_legacy(self):
        self.enable()
        self.model.selector_error = RuntimeError("SENSITIVE_PROVIDER")
        self.assert_failure(await self.post())
        self.assertEqual(self.documents.count_calls, [])
        self.assertEqual(self.rag_inputs, [])
        self.legacy.assert_not_called()

    async def test_rag_route_preserves_ordered_sources_citations_and_aggregate_usage(self):
        self.enable()
        self.model.selection = selection()
        self.model.final = AIMessage(content="Second [2], then first [1]", usage_metadata=FINAL_USAGE)
        response = await self.post(question="Knowledge question")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual([source["chunk_id"] for source in body["sources"]],
                         [source["chunk_id"] for source in SOURCES])
        self.assertEqual([citation["chunk_id"] for citation in body["citations"]],
                         [SOURCES[1]["chunk_id"], SOURCES[0]["chunk_id"]])
        self.assertEqual(body["usage"]["total_tokens"], 13)
        self.assertEqual(self.rag_inputs, [("Knowledge question", {
            "database": self.database, "qdrant_client": self.qdrant, "session_id": None,
        })])
        self.assertEqual(self.documents.count_calls, [])
        self.legacy.assert_not_called()

    async def test_persistent_rag_route_forwards_session_scope_and_persists_citation_identity(self):
        self.enable()
        self.model.selection = selection()
        self.model.final = AIMessage(content="Grounded [2]", usage_metadata=FINAL_USAGE)
        response = await self.post(persistent=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.rag_inputs[0][1]["session_id"], SESSION_ID)
        completed = self.repository.finalized[0]
        self.assertEqual(completed.citations[0].chunk_id, SOURCES[1]["chunk_id"])
        self.assertEqual(completed.usage.total_tokens, 13)
        self.assertIsNone(self.repository.active)

    async def test_missing_actual_usage_stays_null_in_response_and_persisted_message(self):
        self.enable()
        self.model.selection = selection(call(), usage=None)
        response = await self.post(persistent=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["usage"])
        self.assertIsNone(self.repository.finalized[0].usage)

    async def test_persistence_write_failure_is_not_hidden_by_tool_success(self):
        self.enable()
        self.repository.finalize_error = ConversationRepositoryError("Không thể ghi message")
        response = await self.post(persistent=True)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(len(self.documents.count_calls), 1)
        self.assertEqual(len(self.repository.finalize_attempts), 1)
        self.assertEqual(self.repository.finalized, [])
        self.assertEqual(len(self.repository.releases), 1)

    async def test_guard_release_failure_preserves_existing_error_after_acknowledged_commit(self):
        self.enable()
        self.repository.release_error = ConversationRepositoryError("Không thể release guard")
        response = await self.post(persistent=True)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.repository.finalized[0].status, MessageStatus.COMPLETED)
        self.assertEqual(len(self.repository.finalized), 1)
        self.assertEqual(len(self.repository.pairs), 1)
        self.assertIsNotNone(self.repository.active)  # Known C03/C04 behavior, deliberately not repaired.

    async def test_async_cancellation_keeps_service_dedicated_cancelled_generation_path(self):
        self.enable()
        self.model.final_error = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.post(persistent=True)
        self.assertEqual(self.repository.finalized[0].status, MessageStatus.FAILED)
        self.assertEqual(self.repository.finalized[0].error_code, "GENERATION_CANCELLED")
        self.assertEqual(len(self.repository.releases), 1)
        self.assertIsNone(self.repository.active)

    async def test_enabled_json_missing_mongo_is_503_before_selector_or_service(self):
        self.enable()
        self.app.state.cloud_connections.mongodb.database = None
        response = await self.post()
        self.assertEqual(response.status_code, 503)
        self.compose.assert_not_called()
        self.service_factory.assert_not_called()

    async def test_enabled_rag_missing_qdrant_fails_safely_without_metadata_fallback(self):
        self.enable()
        self.app.state.cloud_connections.qdrant.client = None
        self.model.selection = selection()
        self.assert_failure(await self.post())
        self.assertEqual(self.documents.count_calls, [])
        self.assertEqual(self.model.final_inputs, [])

    async def test_json_request_response_contracts_have_no_new_tool_fields(self):
        self.enable()
        response = await self.post()
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(set(body), {
            "request_id", "session_id", "user_message_id", "assistant_message_id", "answer", "sources",
            "citations", "metadata", "usage", "status", "error",
        })
        self.assertEqual(set(ChatRequest.model_fields), {"question", "session_id", "attachments"})
        ChatResponse.model_validate(body)
        self.assertEqual((await self.post(session_id="invalid")).status_code, 422)

    async def test_sse_stays_legacy_when_tool_gate_is_disabled(self):
        prepared = PreparedRagStream(prompt_value="unused", sources=[])
        async def legacy_stream(_prepared):
            yield ProviderStreamChunk("Legacy SSE", None)
        with patch("app.api.routes.chat.prepare_rag_stream", return_value=prepared) as prepare, \
                patch("app.api.routes.chat.astream_rag_answer", legacy_stream), \
                patch("app.api.routes.chat.record_stream_metric"):
            response = await self.client.post("/chat/stream", json={"question": "Count documents"})
        self.assertEqual(response.status_code, 200)
        frames = []
        for frame in response.text.strip().split("\n\n"):
            event, data = frame.splitlines()
            frames.append({"event": event.removeprefix("event: "),
                           "data": json.loads(data.removeprefix("data: "))})
        self.assertEqual([frame["event"] for frame in frames], ["start", "metadata", "delta", "done"])
        SSETranscript.model_validate({"events": frames})
        prepare.assert_called_once()
        self.compose.assert_not_called()
        self.assertEqual(self.model.selector_inputs, [])
        self.assertEqual(self.documents.count_calls, [])


class ToolGateSettingsTests(unittest.TestCase):
    def values(self):
        return {"_env_file": None, "groq_api_key": "offline-placeholder", "embedding_api_key": "offline-placeholder"}

    def test_tool_gate_defaults_disabled_without_changing_model_or_provider_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            configured = Settings(**self.values())
        self.assertFalse(configured.tool_use_enabled)
        self.assertEqual(configured.llm_model, "openai/gpt-oss-120b")
        self.assertEqual(configured.openai_base_url, "https://api.groq.com/openai/v1")

    def test_tool_gate_uses_existing_case_insensitive_environment_conventions(self):
        for name, value, expected in (("TOOL_USE_ENABLED", "true", True),
                                       ("tool_use_enabled", "false", False)):
            with self.subTest(name=name, value=value), patch.dict(os.environ, {name: value}, clear=True):
                self.assertEqual(Settings(**self.values()).tool_use_enabled, expected)

    def test_invalid_tool_gate_environment_value_is_rejected(self):
        with patch.dict(os.environ, {"TOOL_USE_ENABLED": "not-a-boolean"}, clear=True):
            with self.assertRaises(ValidationError):
                Settings(**self.values())

    def test_root_environment_template_keeps_the_gate_disabled(self):
        template = Path(__file__).parents[3] / ".env.example"
        self.assertIn("TOOL_USE_ENABLED=false", template.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
