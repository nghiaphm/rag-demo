"""Shared facade acceptance with native SDK messages and offline dependencies."""

import asyncio
import ast
import json
import socket
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.utils import convert_to_openai_messages
from langchain_core.prompt_values import ChatPromptValue
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.chat_orchestration import (
    ChatOrchestrationError,
    ChatOrchestrator,
    FINAL_INSTRUCTION,
    SELECTOR_INSTRUCTION,
    UsageLedger,
    estimate_context_tokens,
)
from app.citation_mapping import map_verified_citations
from app.context_budget import ContextBudgetConfig
from app.conversation_models import MessageRecord, MessageRole, MessageStatus, SessionScope, SessionScopeMode
from app.conversation_repository import SessionNotFoundError
from app.document_models import DocumentStatus
from app.document_repository import RepositoryError, RepositoryQueryTimeoutError
from app.history import HistoryTurn
from app.query_rewriting import QueryRewriteResult, RewriteMetrics, RewriteStatus
from app.rag.pipeline import PreparedRagStream

SELECTOR_USAGE = {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3}
FINAL_USAGE = {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10}
CONFIG = ContextBudgetConfig(8192, 1024, 2048, 3584, 512, 1024)
SESSION_ID = str(UUID(int=1))
DOC_ID = str(UUID(int=2))
VERSION_ID = str(UUID(int=3))
SOURCES = [{
    "document_id": DOC_ID, "version_id": VERSION_ID, "chunk_id": str(UUID(int=index + 4)),
    "file_name": f"file-{index}.md", "page": index,
} for index in (1, 0)]


def call(name="count_documents", arguments=None, call_id="call-1"):
    return {"name": name, "args": {} if arguments is None else arguments, "id": call_id, "type": "tool_call"}


def selection(*calls, usage=SELECTOR_USAGE):
    return AIMessage(content="DRAFT: never use this as the final answer.",
                     tool_calls=list(calls), usage_metadata=usage)


def turn(index, content="History"):
    request_id = str(UUID(int=index + 100))
    return HistoryTurn(
        user=MessageRecord(message_id=str(UUID(int=index * 2 + 200)), session_id=SESSION_ID,
                           request_id=request_id, sequence=index * 2 + 1,
                           role=MessageRole.USER, status=MessageStatus.COMPLETED, content=content),
        assistant=MessageRecord(message_id=str(UUID(int=index * 2 + 201)), session_id=SESSION_ID,
                                request_id=request_id, sequence=index * 2 + 2,
                                role=MessageRole.ASSISTANT, status=MessageStatus.COMPLETED,
                                content=f"Response {index}"),
    )


class FakeModel:
    def __init__(self, response=None):
        self.selection = response if response is not None else selection()
        self.final = AIMessage(content="Grounded answer", usage_metadata=FINAL_USAGE)
        self.chunks = [AIMessageChunk(content="Grounded "),
                       AIMessageChunk(content="answer", usage_metadata=FINAL_USAGE)]
        self.binds, self.selector_inputs, self.final_inputs = [], [], []
        self.selector_error = self.final_error = self.bind_error = None
        self.selector_hook = self.final_hook = None
        self.stream_closed = 0

    def bind_tools(self, schemas, **options):
        self.binds.append((schemas, options))
        if self.bind_error:
            raise self.bind_error
        return SimpleNamespace(ainvoke=self.select)

    async def select(self, messages, **options):
        self.selector_inputs.append((messages, options))
        if self.selector_hook:
            await self.selector_hook()
        if self.selector_error:
            raise self.selector_error
        return self.selection

    async def ainvoke(self, messages, **options):
        self.final_inputs.append((messages, options))
        if self.final_hook:
            await self.final_hook()
        if self.final_error:
            raise self.final_error
        return self.final

    async def astream(self, messages, **options):
        self.final_inputs.append((messages, options))
        try:
            if self.final_hook:
                await self.final_hook()
            if self.final_error:
                raise self.final_error
            for chunk in self.chunks:
                yield chunk
        finally:
            self.stream_closed += 1


class FakeQueries:
    def __init__(self):
        self.calls = []
        self.error = self.hook = None
        self.count_data = {"count": 6, "unit": "document", "scope": "library", "include_deleted": False}
        self.list_data = {
            "items": [{"document_id": DOC_ID, "file_name": "guide.md", "status": "INDEXED",
                       "active_version_id": VERSION_ID, "created_at": "2026-10-30T00:00:00+00:00",
                       "updated_at": "2026-10-30T00:00:00+00:00"}],
            "scope": "library", "include_deleted": False, "offset": 0, "limit": 10,
            "returned_count": 1, "has_more": True, "next_offset": 1, "truncated_by_bytes": False,
            "order": ["created_at:desc", "document_id:desc"],
        }

    def count_documents(self, **arguments):
        self.calls.append(("count_documents", arguments))
        if self.hook:
            self.hook()
        if self.error:
            raise self.error
        return dict(self.count_data)

    def list_documents(self, **arguments):
        self.calls.append(("list_documents", arguments))
        if self.hook:
            self.hook()
        if self.error:
            raise self.error
        return dict(self.list_data)


class FakeHistory:
    def __init__(self, turns=()):
        self.turns, self.inputs = turns, []

    def load(self, session_id):
        self.inputs.append(session_id)
        return SimpleNamespace(turns=self.turns)


class ChatOrchestrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        network = patch.object(socket.socket, "connect", side_effect=AssertionError("offline only"))
        self.connect = network.start()
        self.addCleanup(network.stop)
        provider = patch("app.chat_orchestration.get_llm", side_effect=AssertionError("fake model required"))
        self.factory = provider.start()
        self.addCleanup(provider.stop)
        self.queries = FakeQueries()
        self.rag_inputs = []
        self.rag_hook = None
        self.prepared = PreparedRagStream(
            prompt_value=ChatPromptValue(messages=[SystemMessage(content="RAG"), HumanMessage(content="Context")]),
            sources=SOURCES,
            active_version_ids=(VERSION_ID,),
        )

    def tearDown(self):
        self.connect.assert_not_called()
        self.factory.assert_not_called()

    async def rag_prepare(self, question, **dependencies):
        self.rag_inputs.append((question, dependencies))
        if self.rag_hook:
            await self.rag_hook()
        return self.prepared

    def orchestrator(self, model=None, **options):
        parameters = {"llm": model or FakeModel(), "queries": self.queries,
                      "tools_enabled": True, "budget_config": CONFIG, "rag_prepare": self.rag_prepare}
        parameters.update(options)
        return ChatOrchestrator(**parameters)

    async def assert_failure(self, awaitable, code):
        with self.assertRaises(ChatOrchestrationError) as raised:
            await awaitable
        self.assertEqual(raised.exception.code, code)
        self.assertNotIn("SENSITIVE", str(raised.exception))
        return raised.exception

    async def collect(self, orchestrator, plan):
        return [chunk async for chunk in orchestrator.stream_final(plan)]

    async def test_no_tool_routes_to_existing_rag_and_discards_selector_draft(self):
        model = FakeModel()
        orchestrator = self.orchestrator(model)
        database, qdrant = object(), object()
        plan = await orchestrator.prepare_plan("Original question", database=database, qdrant_client=qdrant)
        self.assertEqual(plan.route, "RAG")
        self.assertEqual(self.rag_inputs, [("Original question", {
            "database": database, "qdrant_client": qdrant, "session_id": None,
        })])
        result = await orchestrator.generate_json(plan)
        self.assertEqual(result["answer"], "Grounded answer")
        self.assertEqual(result["sources"], SOURCES)
        self.assertIs(model.final_inputs[0][0], self.prepared.prompt_value)
        self.assertEqual(model.selector_inputs[0][0][-1].content, "Original question")
        self.assertEqual(self.queries.calls, [])
        self.assertEqual(len(model.selector_inputs), 1)

    async def test_count_route_queries_only_after_prepare_and_has_no_retrieval_sources(self):
        model = FakeModel(selection(call()))
        orchestrator = self.orchestrator(model)
        plan = await orchestrator.prepare_plan("How many documents?")
        self.assertEqual(plan.route, "DOCUMENT_TOOLS")
        self.assertEqual(self.queries.calls, [])
        self.assertEqual(self.rag_inputs, [])
        result = await orchestrator.generate_json(plan)
        self.assertEqual(self.queries.calls, [("count_documents", {"include_deleted": False})])
        self.assertEqual(result["sources"], [])
        self.assertEqual(len(model.binds), 1)
        self.assertEqual({tool["function"]["name"] for tool in model.binds[0][0]},
                         {"count_documents", "list_documents"})
        self.assertEqual(model.binds[0][1], {"tool_choice": "auto"})
        self.assertEqual(self.rag_inputs, [])

    async def test_list_route_enforces_pagination_notice_in_instruction_and_answer(self):
        model = FakeModel(selection(call("list_documents")))
        orchestrator = self.orchestrator(model)
        result = await orchestrator.generate_json(await orchestrator.prepare_plan("List documents"))
        self.assertIn("Danh sách này chưa đầy đủ", result["answer"])
        self.assertIn("next_offset=1", result["answer"])
        self.assertIn("has_more=true", model.final_inputs[0][0][0].content)
        self.assertIn("offset>0", model.final_inputs[0][0][0].content)
        self.assertEqual(result["sources"], [])
        self.assertEqual(len(self.queries.calls), 1)

    async def test_nonzero_offset_is_not_labelled_the_whole_library(self):
        self.queries.list_data.update(offset=10, has_more=False, next_offset=None)
        orchestrator = self.orchestrator(FakeModel(selection(call("list_documents", {"offset": 10}))))
        result = await orchestrator.generate_json(await orchestrator.prepare_plan("Next page"))
        self.assertIn("không phải toàn bộ thư viện", result["answer"])
        self.assertIn("offset 10", result["answer"])

    async def test_complete_first_page_does_not_invent_a_next_page_notice(self):
        self.queries.list_data.update(has_more=False, next_offset=None)
        orchestrator = self.orchestrator(FakeModel(selection(call("list_documents"))))
        result = await orchestrator.generate_json(await orchestrator.prepare_plan("List"))
        self.assertEqual(result["answer"], "Grounded answer")

    async def test_two_calls_and_native_tool_messages_preserve_ids_and_order(self):
        model = FakeModel(selection(call("list_documents", call_id="first"), call(call_id="second")))
        orchestrator = self.orchestrator(model)
        await orchestrator.generate_json(await orchestrator.prepare_plan("List and count"))
        messages, options = model.final_inputs[0]
        native = convert_to_openai_messages(messages)
        assistant = next(message for message in native if message["role"] == "assistant")
        results = [message for message in native if message["role"] == "tool"]
        self.assertEqual([item["id"] for item in assistant["tool_calls"]], ["first", "second"])
        self.assertEqual([message["tool_call_id"] for message in results], ["first", "second"])
        self.assertEqual([json.loads(message["content"])["tool"] for message in results],
                         ["list_documents", "count_documents"])
        self.assertEqual(json.loads(results[0]["content"])["data"], self.queries.list_data)
        self.assertEqual(options, {"tools": [], "tool_choice": "none", "max_tokens": 1024})

    async def test_unknown_tool_is_controlled_before_any_query_or_rag_fallback(self):
        model = FakeModel(selection(call("analyze_document")))
        await self.assert_failure(self.orchestrator(model).prepare_plan("Analyze"), "TOOL_UNKNOWN")
        self.assertEqual(self.queries.calls, [])
        self.assertEqual(self.rag_inputs, [])
        self.assertEqual(model.final_inputs, [])

    async def test_missing_duplicate_oversized_ids_and_more_than_two_calls_fail_prepare(self):
        for calls in (
            [call(call_id=None)], [call(call_id="")], [call(call_id="x" * 129)],
            [call(call_id="same"), call("list_documents", call_id="same")],
            [call(call_id=str(index)) for index in range(3)],
        ):
            with self.subTest(calls=calls):
                await self.assert_failure(self.orchestrator(FakeModel(selection(*calls))).prepare_plan("Question"),
                                          "TOOL_LIMIT_EXCEEDED")
        self.assertEqual(self.queries.calls, [])

    async def test_invalid_second_call_arguments_prevent_execution_of_first_call(self):
        for arguments in ({"offset": True}, {"limit": 21}, {"status": "INDEXED"}, {"max_time_ms": 1}):
            response = selection(call(call_id="a"), call("list_documents", arguments, "b"))
            await self.assert_failure(self.orchestrator(FakeModel(response)).prepare_plan("Question"),
                                      "TOOL_INVALID_ARGUMENTS")
        self.assertEqual(self.queries.calls, [])

    async def test_invalid_sdk_tool_calls_never_become_a_rag_question(self):
        response = AIMessage(content="DRAFT", invalid_tool_calls=[{
            "name": "count_documents", "args": "{", "id": "bad", "error": "SENSITIVE", "type": "invalid_tool_call",
        }])
        await self.assert_failure(self.orchestrator(FakeModel(response)).prepare_plan("Count"),
                                  "TOOL_INVALID_ARGUMENTS")
        self.assertEqual(self.rag_inputs, [])

    async def test_raw_sdk_arguments_keep_duplicate_key_and_payload_size_validation(self):
        for raw in ('{"include_deleted":false,"include_deleted":true}', "{}" + " " * 2048):
            response = selection(call())
            response.additional_kwargs["tool_calls"] = [{
                "id": "call-1", "type": "function", "function": {"name": "count_documents", "arguments": raw},
            }]
            await self.assert_failure(self.orchestrator(FakeModel(response)).prepare_plan("Count"),
                                      "TOOL_INVALID_ARGUMENTS")
        self.assertEqual(self.queries.calls, [])

    async def test_raw_and_native_calls_must_agree_before_execution(self):
        response = selection(call())
        response.additional_kwargs["tool_calls"] = [{
            "id": "other-id", "function": {"name": "count_documents", "arguments": "{}"},
        }]
        await self.assert_failure(self.orchestrator(FakeModel(response)).prepare_plan("Count"),
                                  "TOOL_INVALID_ARGUMENTS")

    async def test_raw_valid_json_maps_to_the_same_native_protocol(self):
        response = selection(call())
        response.additional_kwargs["tool_calls"] = [{
            "id": "call-1", "type": "function", "function": {"name": "count_documents", "arguments": "{}"},
        }]
        orchestrator = self.orchestrator(FakeModel(response))
        await orchestrator.generate_json(await orchestrator.prepare_plan("Count"))
        self.assertEqual(len(self.queries.calls), 1)

    async def test_natural_language_or_user_written_function_text_is_not_executed(self):
        model = FakeModel(selection())
        model.selection.content = 'count_documents({"include_deleted": true})'
        orchestrator = self.orchestrator(model)
        result = await orchestrator.generate_json(await orchestrator.prepare_plan("Please run count_documents()"))
        self.assertEqual(result["answer"], "Grounded answer")
        self.assertEqual(self.queries.calls, [])
        self.assertEqual(len(self.rag_inputs), 1)

    async def test_tool_error_stops_before_final_generation_for_json_and_stream(self):
        for error, code in ((RepositoryError("SENSITIVE"), "TOOL_QUERY_FAILED"),
                            (RepositoryQueryTimeoutError("SENSITIVE"), "TOOL_TIMEOUT")):
            for streaming in (False, True):
                with self.subTest(error=type(error).__name__, streaming=streaming):
                    self.queries.error = error
                    model = FakeModel(selection(call()))
                    orchestrator = self.orchestrator(model)
                    plan = await orchestrator.prepare_plan("Count")
                    operation = self.collect(orchestrator, plan) if streaming else orchestrator.generate_json(plan)
                    await self.assert_failure(operation, code)
                    self.assertEqual(model.final_inputs, [])
                    self.assertEqual(self.rag_inputs, [])

    async def test_selector_failure_has_no_retry_provider_switch_or_rag_fallback(self):
        for bind_failure in (False, True):
            model = FakeModel()
            if bind_failure:
                model.bind_error = NotImplementedError("SENSITIVE")
            else:
                model.selector_error = RuntimeError("SENSITIVE")
            await self.assert_failure(self.orchestrator(model).prepare_plan("Count"), "TOOL_PROVIDER_UNAVAILABLE")
            self.assertLessEqual(len(model.selector_inputs), 1)
            self.assertEqual(model.final_inputs, [])
            self.assertEqual(self.rag_inputs, [])

    async def test_final_generation_cannot_open_a_second_tool_round(self):
        model = FakeModel(selection(call()))
        model.final = selection(call("list_documents", call_id="new-round"))
        orchestrator = self.orchestrator(model)
        await self.assert_failure(orchestrator.generate_json(await orchestrator.prepare_plan("Count")),
                                  "CHAT_PROVIDER_PROTOCOL_ERROR")
        self.assertEqual(len(self.queries.calls), 1)
        self.assertEqual(len(model.selector_inputs), 1)
        self.assertEqual(len(model.final_inputs), 1)

    async def test_stream_rejects_tool_call_chunks_without_emitting_raw_protocol(self):
        model = FakeModel(selection(call()))
        model.chunks = [AIMessageChunk(content="", tool_call_chunks=[{
            "name": "list_documents", "args": "{}", "id": "new", "index": 0,
        }])]
        orchestrator = self.orchestrator(model)
        plan = await orchestrator.prepare_plan("Count")
        emitted = []
        with self.assertRaises(ChatOrchestrationError) as raised:
            async for chunk in orchestrator.stream_final(plan):
                emitted.append(chunk)
        self.assertEqual(raised.exception.code, "CHAT_PROVIDER_PROTOCOL_ERROR")
        self.assertEqual(emitted, [])
        self.assertEqual(len(self.queries.calls), 1)

    async def test_json_and_stream_share_routing_notice_and_usage_policy(self):
        bodies, usages = [], []
        for streaming in (False, True):
            model = FakeModel(selection(call("list_documents")))
            model.final = AIMessage(content=" \nAnswer", usage_metadata=FINAL_USAGE)
            model.chunks = [AIMessageChunk(content=" \n"), AIMessageChunk(content="Answer"),
                            AIMessageChunk(content="", usage_metadata=FINAL_USAGE)]
            orchestrator = self.orchestrator(model)
            plan = await orchestrator.prepare_plan("List")
            if streaming:
                chunks = await self.collect(orchestrator, plan)
                bodies.append("".join(chunk.content or "" for chunk in chunks))
                usages.append(chunks[-1].usage)
                self.assertTrue(all(chunk.usage is None for chunk in chunks[:-1]))
                self.assertIsNone(chunks[-1].content)
            else:
                result = await orchestrator.generate_json(plan)
                bodies.append(result["answer"])
                usages.append(result["usage"])
            self.assertEqual(len(model.selector_inputs), 1)
            self.assertEqual(plan.sources, [])
        self.assertEqual(bodies[0], bodies[1])
        self.assertTrue(bodies[0].startswith("Danh sách này chưa đầy đủ"))
        self.assertEqual(usages, [{"input_tokens": 9, "output_tokens": 4, "total_tokens": 13}] * 2)

    async def test_usage_aggregates_actual_invocations_not_cumulative_snapshots(self):
        model = FakeModel(selection(call()))
        model.chunks = [
            AIMessageChunk(content="A", usage_metadata={"input_tokens": 7, "output_tokens": 1, "total_tokens": 8}),
            AIMessageChunk(content="B", usage_metadata=FINAL_USAGE),
            AIMessageChunk(content=""),
        ]
        orchestrator = self.orchestrator(model)
        plan = await orchestrator.prepare_plan("Count")
        chunks = await self.collect(orchestrator, plan)
        self.assertEqual(chunks[-1].usage, {"input_tokens": 9, "output_tokens": 4, "total_tokens": 13})
        self.assertEqual([stage for stage, _ in plan.ledger.entries], ["selector", "final"])

    async def test_missing_actual_usage_never_exposes_a_partial_total_as_full(self):
        for missing in ("selector", "final"):
            for streaming in (False, True):
                model = FakeModel(selection(call(), usage=None if missing == "selector" else SELECTOR_USAGE))
                if missing == "final":
                    model.final = AIMessage(content="Answer")
                    model.chunks = [AIMessageChunk(content="Answer")]
                orchestrator = self.orchestrator(model)
                plan = await orchestrator.prepare_plan("Count")
                if streaming:
                    self.assertIsNone((await self.collect(orchestrator, plan))[-1].usage)
                else:
                    self.assertIsNone((await orchestrator.generate_json(plan))["usage"])
                self.assertIsNone(plan.usage)

    async def test_rewrite_actual_usage_is_included_but_estimates_make_aggregate_unknown(self):
        for source, calls, expected in (("provider", 1, 18), ("estimated", 1, None), ("none", 0, 13)):
            self.prepared = replace(self.prepared, rewrite=QueryRewriteResult(
                "Question", "Rewritten", source == "provider", RewriteStatus.REWRITTEN,
                "history", RewriteMetrics(calls, 1.0, 4, 1, 5, source),
            ))
            orchestrator = self.orchestrator(FakeModel(selection()))
            result = await orchestrator.generate_json(await orchestrator.prepare_plan("Question"))
            self.assertEqual(result["usage"]["total_tokens"] if result["usage"] else None, expected)

    async def test_default_disabled_facade_preserves_legacy_rag_without_selector_or_new_model_options(self):
        model = FakeModel(selection(call()))  # Even this response must never be requested.
        orchestrator = ChatOrchestrator(llm=model, rag_prepare=self.rag_prepare, budget_config=CONFIG)
        plan = await orchestrator.prepare_plan("Question")
        self.assertFalse(plan.tools_enabled)
        self.assertIsNone(plan.deadline)
        result = await orchestrator.generate_json(plan)
        self.assertEqual(result, {"answer": "Grounded answer", "sources": SOURCES, "usage": FINAL_USAGE})
        self.assertEqual(model.binds, [])
        self.assertEqual(model.selector_inputs, [])
        self.assertEqual(model.final_inputs[0][1], {})

    async def test_default_disabled_stream_retains_legacy_chunk_usage(self):
        model = FakeModel()
        orchestrator = self.orchestrator(model, tools_enabled=False)
        chunks = await self.collect(orchestrator, await orchestrator.prepare_plan("Question"))
        self.assertEqual([chunk.content for chunk in chunks], ["Grounded ", "answer"])
        self.assertEqual(chunks[-1].usage, FINAL_USAGE)
        self.assertEqual(model.selector_inputs, [])

    async def test_history_prunes_whole_old_turns_and_selector_keeps_original_question(self):
        old, recent = turn(0, "old " * 500), turn(1, "recent reference")
        loader = FakeHistory((old, recent))
        model = FakeModel(selection(call()))
        orchestrator = self.orchestrator(model, history_loader=loader,
                                         budget_config=replace(CONFIG, history_max_tokens=100))
        plan = await orchestrator.prepare_plan("Original metadata question", session_id=SESSION_ID)
        messages = model.selector_inputs[0][0]
        self.assertEqual([message.type for message in messages], ["system", "human", "ai", "human"])
        self.assertEqual(messages[1].content, "recent reference")
        self.assertEqual(messages[-1].content, "Original metadata question")
        self.assertEqual(plan.history_turns, (recent,))
        self.assertEqual(loader.inputs, [SESSION_ID])

    async def test_rag_uses_existing_scope_rewrite_retriever_order_and_citation_identity(self):
        history = (turn(0),)
        deleted_id = str(UUID(int=999))
        loaded = SimpleNamespace(turns=history, scope=SessionScope(
            mode=SessionScopeMode.SELECTED_DOCUMENTS, document_ids=[DOC_ID, deleted_id],
        ))
        repository = SimpleNamespace(get_document=lambda identifier: SimpleNamespace(
            status=DocumentStatus.INDEXED if identifier == DOC_ID else DocumentStatus.DELETED,
            active_version_id=VERSION_ID, deleted_at=None,
        ))
        documents = [Document(page_content=f"Evidence {index}", metadata=dict(source))
                     for index, source in enumerate(SOURCES)]
        retrieval_inputs = []
        retriever = SimpleNamespace(invoke=lambda question: retrieval_inputs.append(question) or documents)
        async def rewrite(question, turns):
            self.assertEqual(question, "Original question")
            return QueryRewriteResult(question, "Rewritten retrieval", True, RewriteStatus.REWRITTEN,
                                      "history", RewriteMetrics(1, 1, 4, 1, 5, "provider"))
        model = FakeModel(selection())
        model.final = AIMessage(content="Grounded [2]", usage_metadata=FINAL_USAGE)
        orchestrator = self.orchestrator(model, rag_prepare=None, history_loader=FakeHistory(history))
        with patch("app.rag.pipeline.MongoDocumentRepository", return_value=repository), \
                patch("app.rag.pipeline.MongoConversationRepository", return_value=object()), \
                patch("app.rag.pipeline.ConversationHistoryLoader") as history_type, \
                patch("app.rag.pipeline.get_retriever", return_value=retriever) as build_retriever, \
                patch("app.rag.pipeline.create_query_rewriter", return_value=SimpleNamespace(rewrite=rewrite)):
            history_type.return_value.load.return_value = loaded
            plan = await orchestrator.prepare_plan("Original question", database=object(),
                                                   qdrant_client=object(), session_id=SESSION_ID)
            result = await orchestrator.generate_json(plan)
        self.assertEqual(build_retriever.call_args.kwargs["active_version_ids"], (VERSION_ID,))
        self.assertEqual(plan.rag.active_version_ids, (VERSION_ID,))
        self.assertEqual(retrieval_inputs, ["Rewritten retrieval"])
        self.assertEqual([source["chunk_id"] for source in result["sources"]],
                         [source["chunk_id"] for source in SOURCES])
        self.assertEqual(map_verified_citations(result["answer"], result["sources"])[0]["chunk_id"],
                         SOURCES[1]["chunk_id"])
        self.assertEqual(model.selector_inputs[0][0][-1].content, "Original question")
        self.assertEqual(result["usage"]["total_tokens"], 18)

    async def test_selector_schema_budget_overflow_fails_before_model_or_queries(self):
        small = ContextBudgetConfig(700, 512, 1, 1, 64, 64)
        model = FakeModel(selection(call()))
        orchestrator = self.orchestrator(model, budget_config=small)
        await self.assert_failure(orchestrator.prepare_plan("Count"), "CHAT_CONTEXT_LIMIT")
        self.assertEqual(model.selector_inputs, [])
        self.assertEqual(self.queries.calls, [])

    async def test_original_question_is_never_truncated_to_fit_selector(self):
        model = FakeModel(selection(call()))
        orchestrator = self.orchestrator(model, budget_config=replace(CONFIG, query_max_tokens=5))
        await self.assert_failure(orchestrator.prepare_plan("original " * 50), "CHAT_CONTEXT_LIMIT")
        self.assertEqual(model.selector_inputs, [])

    async def test_tool_results_that_cannot_fit_after_history_pruning_fail_without_final_request(self):
        self.queries.count_data["padding"] = "x" * 6000
        model = FakeModel(selection(call()))
        small = ContextBudgetConfig(2000, 700, 100, 100, 100, 512)
        orchestrator = self.orchestrator(model, budget_config=small)
        plan = await orchestrator.prepare_plan("Count")
        await self.assert_failure(orchestrator.generate_json(plan), "CHAT_CONTEXT_LIMIT")
        self.assertEqual(len(self.queries.calls), 1)
        self.assertEqual(model.final_inputs, [])

    async def test_context_counter_includes_tool_schemas_call_ids_json_and_reserve(self):
        schemas = self.orchestrator()._schemas()
        for schema in schemas:
            self.assertEqual(convert_to_openai_tool(schema), schema)
        base = [SystemMessage(content="System"), HumanMessage(content="Question")]
        with_calls = [*base, selection(call(call_id="x" * 100)),
                      ToolMessage(content=json.dumps({"payload": "😀" * 200}), tool_call_id="x" * 100)]
        self.assertGreater(estimate_context_tokens(base, CONFIG, schemas), estimate_context_tokens(base, CONFIG))
        self.assertGreater(estimate_context_tokens(with_calls, CONFIG), estimate_context_tokens(base, CONFIG))
        wire = convert_to_openai_messages(with_calls)
        self.assertEqual(wire[-1]["tool_call_id"], "x" * 100)
        self.assertEqual(json.loads(wire[-1]["content"])["payload"], "😀" * 200)

    async def test_one_shared_deadline_survives_prepare_tools_and_final_generation(self):
        clock = [monotonic()]
        initial = clock[0]
        model = FakeModel(selection(call()))
        async def selector_hook():
            clock[0] += 0.2
        async def final_hook():
            clock[0] += 0.2
        model.selector_hook, model.final_hook = selector_hook, final_hook
        orchestrator = self.orchestrator(model)
        from app.tool_use.executor import ToolExecutor
        original_execute, passed_deadlines = ToolExecutor.execute, []
        async def execute(executor, calls, *, deadline=None):
            passed_deadlines.append(deadline)
            return await original_execute(executor, calls, deadline=deadline)
        with patch("app.chat_orchestration.monotonic", side_effect=lambda: clock[0]), \
                patch("app.chat_orchestration.ToolExecutor.execute", new=execute):
            plan = await orchestrator.prepare_plan("Count", deadline=initial + 1)
            result = await orchestrator.generate_json(plan)
        self.assertEqual(plan.deadline, initial + 1)
        self.assertEqual(passed_deadlines, [plan.deadline])
        self.assertEqual(result["usage"]["total_tokens"], 13)

    async def test_expired_plan_never_starts_tools_or_final_generation(self):
        model = FakeModel(selection(call()))
        orchestrator = self.orchestrator(model)
        plan = await orchestrator.prepare_plan("Count")
        plan.deadline = monotonic() - 1
        await self.assert_failure(orchestrator.generate_json(plan), "CHAT_TIMEOUT")
        self.assertEqual(self.queries.calls, [])
        self.assertEqual(model.final_inputs, [])

    async def test_late_final_response_does_not_reset_the_deadline_or_start_a_fallback(self):
        clock = [monotonic()]
        initial = clock[0]
        model = FakeModel(selection())
        async def advance_selector():
            clock[0] += 0.4
        async def advance_preparation():
            clock[0] += 0.3
        async def advance_final():
            clock[0] += 0.4
        model.selector_hook, model.final_hook = advance_selector, advance_final
        self.rag_hook = advance_preparation
        orchestrator = self.orchestrator(model)
        with patch("app.chat_orchestration.monotonic", side_effect=lambda: clock[0]):
            plan = await orchestrator.prepare_plan("Question", deadline=initial + 1)
            await self.assert_failure(orchestrator.generate_json(plan), "CHAT_TIMEOUT")
        self.assertEqual(plan.deadline, initial + 1)
        self.assertEqual(len(model.selector_inputs), 1)
        self.assertEqual(len(model.final_inputs), 1)
        self.assertEqual(self.queries.calls, [])

    async def test_selector_has_fifteen_second_limit_and_turn_deadline_is_capped(self):
        model = FakeModel(selection(call()))
        original_wait = asyncio.wait_for
        orchestrator = self.orchestrator(model)
        initial = monotonic()
        with patch("app.chat_orchestration.asyncio.wait_for", wraps=original_wait) as wait:
            plan = await orchestrator.prepare_plan("Count", deadline=initial + 10000)
        self.assertEqual(wait.call_args.args[1], 15.0)
        self.assertLessEqual(plan.deadline, initial + 121)

    async def test_selector_timeout_is_controlled_and_never_falls_back(self):
        started = asyncio.Event()
        async def block():
            started.set()
            await asyncio.Event().wait()
        model = FakeModel(selection(call()))
        model.selector_hook = block
        with patch("app.chat_orchestration.MAX_SELECTOR_SECONDS", 0.01):
            await self.assert_failure(self.orchestrator(model).prepare_plan("Count"), "CHAT_TIMEOUT")
        self.assertTrue(started.is_set())
        self.assertEqual(self.queries.calls, [])
        self.assertEqual(self.rag_inputs, [])

    async def test_cancelling_selector_never_schedules_tools_rag_or_final_generation(self):
        started = asyncio.Event()
        async def block():
            started.set()
            await asyncio.Event().wait()
        model = FakeModel(selection(call()))
        model.selector_hook = block
        task = asyncio.create_task(self.orchestrator(model).prepare_plan("Count"))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.queries.calls, [])
        self.assertEqual(self.rag_inputs, [])
        self.assertEqual(model.final_inputs, [])

    async def test_cancelling_tool_execution_does_not_schedule_final_generation(self):
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        def block():
            started.set()
            try:
                release.wait(2)
            finally:
                finished.set()
        self.queries.hook = block
        model = FakeModel(selection(call()))
        orchestrator = self.orchestrator(model)
        plan = await orchestrator.prepare_plan("Count")
        task = asyncio.create_task(orchestrator.generate_json(plan))
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertEqual(model.final_inputs, [])
            self.assertFalse(finished.is_set())
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
            self.assertTrue(await asyncio.to_thread(finished.wait, 2))

    async def test_cancelling_final_generation_propagates_and_plan_cannot_be_replayed(self):
        started = asyncio.Event()
        async def block():
            started.set()
            await asyncio.Event().wait()
        model = FakeModel(selection(call()))
        model.final_hook = block
        orchestrator = self.orchestrator(model)
        plan = await orchestrator.prepare_plan("Count")
        task = asyncio.create_task(orchestrator.generate_json(plan))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await self.assert_failure(orchestrator.generate_json(plan), "CHAT_PLAN_CONSUMED")
        self.assertEqual(len(self.queries.calls), 1)
        self.assertIsNone(plan.usage)

    async def test_closing_stream_closes_underlying_model_and_does_not_finalize_conversation(self):
        model = FakeModel(selection(call()))
        orchestrator = self.orchestrator(model)
        plan = await orchestrator.prepare_plan("Count")
        iterator = orchestrator.stream_final(plan)
        self.assertEqual((await iterator.__anext__()).content, "Grounded ")
        await iterator.aclose()
        self.assertEqual(model.stream_closed, 1)
        self.assertIsNone(plan.usage)
        self.assertEqual(len(self.queries.calls), 1)

    async def test_cancelling_stream_await_propagates_and_closes_the_model(self):
        started = asyncio.Event()
        async def block():
            started.set()
            await asyncio.Event().wait()
        model = FakeModel(selection(call()))
        model.final_hook = block
        orchestrator = self.orchestrator(model)
        plan = await orchestrator.prepare_plan("Count")
        task = asyncio.create_task(self.collect(orchestrator, plan))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(model.stream_closed, 1)
        self.assertEqual(len(self.queries.calls), 1)
        self.assertEqual(len(model.final_inputs), 1)
        self.assertIsNone(plan.usage)

    async def test_empty_or_whitespace_final_response_is_failure_not_notice_only_success(self):
        for streaming in (False, True):
            model = FakeModel(selection(call("list_documents")))
            model.final = AIMessage(content=" \n", usage_metadata=FINAL_USAGE)
            model.chunks = [AIMessageChunk(content=" \n", usage_metadata=FINAL_USAGE)]
            orchestrator = self.orchestrator(model)
            plan = await orchestrator.prepare_plan("List")
            if streaming:
                emitted = []
                with self.assertRaises(ChatOrchestrationError) as raised:
                    async for chunk in orchestrator.stream_final(plan):
                        emitted.append(chunk.content or "")
                self.assertEqual(raised.exception.code, "CHAT_EMPTY_ANSWER")
                self.assertEqual("".join(emitted), " \n")
            else:
                await self.assert_failure(orchestrator.generate_json(plan), "CHAT_EMPTY_ANSWER")
            self.assertEqual(plan.usage["total_tokens"], 13)

    async def test_partial_stream_failure_preserves_text_and_marks_usage_incomplete(self):
        model = FakeModel(selection(call()))
        async def failing_stream(*args, **kwargs):
            yield AIMessageChunk(content="partial", usage_metadata=FINAL_USAGE)
            raise RuntimeError("SENSITIVE_PROVIDER")
        model.astream = failing_stream
        orchestrator = self.orchestrator(model)
        plan = await orchestrator.prepare_plan("Count")
        emitted = []
        with self.assertRaises(ChatOrchestrationError) as raised:
            async for chunk in orchestrator.stream_final(plan):
                emitted.append(chunk.content)
        self.assertEqual(emitted, ["partial"])
        self.assertEqual(raised.exception.code, "CHAT_GENERATION_FAILED")
        self.assertNotIn("SENSITIVE", str(raised.exception))
        self.assertIsNone(plan.usage)

    async def test_typed_session_failure_is_preserved_for_future_http_mapping(self):
        loader = FakeHistory()
        def missing(_session_id):
            raise SessionNotFoundError("Session không tồn tại")
        loader.load = missing
        model = FakeModel()
        with self.assertRaises(SessionNotFoundError):
            await self.orchestrator(model, history_loader=loader).prepare_plan("Question", session_id=SESSION_ID)
        self.assertEqual(model.selector_inputs, [])

    async def test_plan_cannot_be_consumed_twice_or_by_another_facade(self):
        orchestrator = self.orchestrator(FakeModel(selection(call())))
        plan = await orchestrator.prepare_plan("Count")
        await self.assert_failure(self.orchestrator().generate_json(plan), "CHAT_PLAN_CONSUMED")
        await orchestrator.generate_json(plan)
        await self.assert_failure(self.collect(orchestrator, plan), "CHAT_PLAN_CONSUMED")
        self.assertEqual(len(self.queries.calls), 1)

    async def test_missing_tool_dependency_is_a_controlled_preparation_failure(self):
        model = FakeModel(selection(call()))
        await self.assert_failure(self.orchestrator(model, queries=None).prepare_plan("Count"),
                                  "CHAT_DEPENDENCY_UNAVAILABLE")
        self.assertEqual(model.final_inputs, [])

    async def test_usage_ledger_is_request_local_and_excludes_missing_actual_counts(self):
        left, right = UsageLedger(), UsageLedger()
        left.complete(left.begin("selector"), SELECTOR_USAGE)
        self.assertEqual(left.total, SELECTOR_USAGE)
        self.assertIsNone(right.total)
        left.begin("final")
        self.assertIsNone(left.total)

    async def test_static_dependencies_do_not_import_api_or_conversation_service_or_execute_code(self):
        path = Path(__file__).parents[1] / "app" / "chat_orchestration.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertNotIn("app.api.chat", imports)
        self.assertNotIn("app.conversation_service", imports)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                self.assertNotIn(ast.unparse(node.func).split(".")[-1], {
                    "eval", "exec", "__import__", "MongoClient", "QdrantClient",
                    "begin_generation", "create_message_pair", "finalize_assistant_message", "release_generation",
                    "_messages", "_select_recent_turns",
                })
        self.assertIn("app.rag.pipeline", imports)
        self.assertIn("app.tool_use.executor", imports)
        self.assertIn("has_more=true", FINAL_INSTRUCTION)
        self.assertIn("knowledge inside documents", SELECTOR_INSTRUCTION)


if __name__ == "__main__":
    unittest.main()
