"""Tool contracts and one-turn execution policy: deterministic I/O, no providers."""

import asyncio
import ast
import json
import socket
import threading
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from app.documents.models import DocumentRecord
from app.documents.queries import DocumentQueries, DocumentQueryOutputLimitError
from app.documents.repository import (
    DocumentQueryParameterError,
    RepositoryError,
    RepositoryQueryTimeoutError,
)
from app.tool_use.contracts import (
    MAX_ARGUMENT_BYTES,
    MAX_BATCH_RESULT_BYTES,
    MAX_RESULT_BYTES,
    ToolCall,
    ToolContractError,
    failure_result,
    normalize_result,
    serialize_result,
    success_result,
    validate_arguments,
)
from app.documents.tool_handlers import (
    count_documents,
    create_document_tool_registry,
    document_tool_definitions,
    list_documents,
)
from app.tool_use.executor import ToolExecutor


class FakeDocumentQueries:
    def __init__(self):
        self.calls = []
        self.error = None
        self.count_hook = None
        self.list_hook = None
        self.count_data = {
            "count": 6, "unit": "document", "scope": "library", "include_deleted": False,
        }
        self.list_data = {
            "items": [{"document_id": "id-1", "file_name": "guide.md", "status": "INDEXED",
                       "active_version_id": None, "created_at": "2026-10-30T12:00:00+00:00",
                       "updated_at": "2026-10-30T12:00:00+00:00"}],
            "scope": "library", "include_deleted": False, "offset": 0, "limit": 10,
            "returned_count": 1, "has_more": True, "next_offset": 1,
            "truncated_by_bytes": False, "order": ["created_at:desc", "document_id:desc"],
        }

    def count_documents(self, **arguments):
        self.calls.append(("count_documents", arguments))
        if self.count_hook:
            self.count_hook()
        if self.error:
            raise self.error
        return deepcopy(self.count_data)

    def list_documents(self, **arguments):
        self.calls.append(("list_documents", arguments))
        if self.list_hook:
            self.list_hook()
        if self.error:
            raise self.error
        return deepcopy(self.list_data)


class OfflineMixin:
    def setUp(self):
        super().setUp()
        network = patch.object(socket.socket, "connect", side_effect=AssertionError("offline only"))
        self.connect = network.start()
        self.addCleanup(network.stop)
        self.queries = FakeDocumentQueries()

    def tearDown(self):
        self.connect.assert_not_called()
        super().tearDown()

    def assert_error(self, envelope, code):
        self.assertFalse(envelope["ok"])
        self.assertIsNone(envelope["data"])
        self.assertEqual(envelope["error"]["code"], code)
        self.assertNotIn("SENSITIVE", serialize_result(envelope))


class ToolContractTests(OfflineMixin, unittest.TestCase):
    def test_count_handler_reuses_facade_and_preserves_result(self):
        result = count_documents({"include_deleted": True}, queries=self.queries)
        self.assertTrue(result["ok"])
        self.assertEqual(result["tool"], "count_documents")
        self.assertEqual(result["data"], self.queries.count_data)
        self.assertIsNone(result["error"])
        self.assertEqual(self.queries.calls, [("count_documents", {"include_deleted": True})])

    def test_list_handler_preserves_all_pagination_metadata_without_auto_fetch(self):
        self.queries.list_data.update(offset=7, next_offset=8, limit=20, truncated_by_bytes=True)
        result = list_documents({"offset": 7, "limit": 20}, queries=self.queries)
        self.assertEqual(result["data"], self.queries.list_data)
        self.assertTrue(result["data"]["has_more"])
        self.assertEqual(self.queries.calls, [
            ("list_documents", {"include_deleted": False, "offset": 7, "limit": 20}),
        ])

    def test_empty_argument_objects_apply_defaults(self):
        count_documents({}, queries=self.queries)
        list_documents({}, queries=self.queries)
        self.assertEqual(self.queries.calls, [
            ("count_documents", {"include_deleted": False}),
            ("list_documents", {"include_deleted": False, "offset": 0, "limit": 10}),
        ])

    def test_raw_json_object_is_supported_without_provider_adapter(self):
        self.assertEqual(validate_arguments("list_documents", '{"offset":2,"limit":1}'), {
            "include_deleted": False, "offset": 2, "limit": 1,
        })

    def test_null_scalars_arrays_and_malformed_json_are_rejected(self):
        for value in (None, 0, 1, True, [], "null", "0", "1", '"true"', "true", "[]", "{"):
            for handler in (count_documents, list_documents):
                with self.subTest(value=value, handler=handler.__name__):
                    self.assert_error(handler(value, queries=self.queries), "TOOL_INVALID_ARGUMENTS")
        self.assertEqual(self.queries.calls, [])

    def test_boolean_fields_are_strict(self):
        for value in (None, 0, 1, "true", "false", [], {}):
            for handler in (count_documents, list_documents):
                with self.subTest(value=value, handler=handler.__name__):
                    self.assert_error(handler({"include_deleted": value}, queries=self.queries),
                                      "TOOL_INVALID_ARGUMENTS")
        self.assertEqual(self.queries.calls, [])

    def test_integer_fields_reject_booleans_floats_strings_and_invalid_ranges(self):
        for key, invalid in (
            ("offset", [True, False, 1.0, "1", None, -1, 1 << 63]),
            ("limit", [True, False, 10.0, "10", None, -1, 0, 21]),
        ):
            for value in invalid:
                with self.subTest(key=key, value=value):
                    self.assert_error(list_documents({key: value}, queries=self.queries),
                                      "TOOL_INVALID_ARGUMENTS")
        self.assertEqual(self.queries.calls, [])

    def test_integer_boundaries_and_include_deleted_true_are_valid(self):
        self.assertEqual(validate_arguments("list_documents", {
            "include_deleted": True, "offset": (1 << 63) - 1, "limit": 20,
        }), {"include_deleted": True, "offset": (1 << 63) - 1, "limit": 20})
        self.assertEqual(validate_arguments("list_documents", {"limit": 1})["limit"], 1)

    def test_unknown_filters_and_timeout_arguments_are_forbidden(self):
        for key in ("status", "filename", "date", "query", "max_time_ms", "deadline"):
            for handler in (count_documents, list_documents):
                with self.subTest(key=key, handler=handler.__name__):
                    self.assert_error(handler({key: "SENSITIVE"}, queries=self.queries),
                                      "TOOL_INVALID_ARGUMENTS")
        self.assertEqual(self.queries.calls, [])

    def test_duplicate_json_keys_are_not_silently_overwritten(self):
        result = count_documents('{"include_deleted":true,"include_deleted":false}',
                                 queries=self.queries)
        self.assert_error(result, "TOOL_INVALID_ARGUMENTS")
        self.assertEqual(self.queries.calls, [])

    def test_argument_payload_exact_boundary_and_oversize(self):
        payload = "{}" + " " * (MAX_ARGUMENT_BYTES - 2)
        self.assertTrue(count_documents(payload, queries=self.queries)["ok"])
        self.assert_error(count_documents(payload + " ", queries=self.queries), "TOOL_INVALID_ARGUMENTS")
        self.assertEqual(len(self.queries.calls), 1)

    def test_large_dict_nan_and_non_json_arguments_are_controlled(self):
        for arguments in ({"unexpected": "😀" * 600}, {"limit": float("nan")}, {"limit": object()}):
            self.assert_error(list_documents(arguments, queries=self.queries), "TOOL_INVALID_ARGUMENTS")
        self.assertEqual(self.queries.calls, [])

    def test_result_envelope_has_stable_json_and_a_detached_data_snapshot(self):
        result = success_result("count_documents", self.queries.count_data)
        text = serialize_result(result)
        self.assertEqual(json.loads(text), result)
        self.assertEqual(text, serialize_result(json.loads(text)))
        self.queries.count_data["count"] = 999
        self.assertEqual(result["data"]["count"], 6)

    def test_query_errors_are_not_empty_success_and_never_leak_raw_details(self):
        for error, code in (
            (RepositoryError("SENSITIVE_CONNECTION_STRING"), "TOOL_QUERY_FAILED"),
            (RepositoryQueryTimeoutError("SENSITIVE_QUERY"), "TOOL_TIMEOUT"),
            (DocumentQueryOutputLimitError("SENSITIVE_OUTPUT"), "TOOL_OUTPUT_LIMIT"),
            (DocumentQueryParameterError("SENSITIVE_ARGUMENT"), "TOOL_INVALID_ARGUMENTS"),
            (RuntimeError("SENSITIVE_TRACE"), "TOOL_QUERY_FAILED"),
        ):
            for handler in (count_documents, list_documents):
                with self.subTest(error=type(error).__name__, handler=handler.__name__):
                    self.queries.error = error
                    result = handler({}, queries=self.queries)
                    self.assert_error(result, code)
                    self.assertEqual(result["error"]["retryable"], code == "TOOL_TIMEOUT")
        self.assertEqual(len(self.queries.calls), 10)  # One call per attempt, no retry.

    def test_handler_output_size_failure_is_controlled_without_string_truncation(self):
        self.queries.list_data["items"][0]["file_name"] = "😀" * 3000
        self.assert_error(list_documents({}, queries=self.queries), "TOOL_OUTPUT_LIMIT")
        self.assertEqual(len(self.queries.calls), 1)

    def test_real_document_facade_byte_reserve_fits_the_complete_tool_envelope(self):
        records = [DocumentRecord(file_name="😀" * 255) for _ in range(21)]
        class Repository:
            calls = 0

            def list_documents_for_tools(self, *, include_deleted, offset, limit):
                self.calls += 1
                return records[offset:offset + limit]
        repository = Repository()
        queries = DocumentQueries(repository)
        expected = queries.list_documents(limit=20)
        result = list_documents({"limit": 20}, queries=queries)
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"], expected)
        self.assertTrue(result["data"]["truncated_by_bytes"])
        self.assertEqual(result["data"]["next_offset"], result["data"]["returned_count"])
        self.assertLessEqual(len(serialize_result(result).encode("utf-8")), MAX_RESULT_BYTES)
        self.assertEqual(repository.calls, 2)  # One explicit facade call, one handler call.

    def test_handler_does_not_swallow_cancellation(self):
        self.queries.error = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            count_documents({}, queries=self.queries)

    def test_injected_error_messages_are_replaced_by_safe_contract_messages(self):
        raw = {"ok": False, "tool": "count_documents", "data": None,
               "error": {"code": "TOOL_QUERY_FAILED", "message": "SENSITIVE", "retryable": True}}
        result = normalize_result("count_documents", raw)
        self.assert_error(result, "TOOL_QUERY_FAILED")
        self.assertFalse(result["error"]["retryable"])

    def test_invalid_handler_envelopes_are_rejected(self):
        for raw in (None, {}, {"ok": True},
                    {"ok": True, "tool": "list_documents", "data": {}, "error": None},
                    {"ok": 1, "tool": "count_documents", "data": {}, "error": None},
                    {"ok": False, "tool": "count_documents", "data": None,
                     "error": {"code": "TOOL_PROVIDER_UNAVAILABLE"}}):
            with self.subTest(raw=raw):
                with self.assertRaises(ToolContractError):
                    normalize_result("count_documents", raw)

    def test_registry_and_descriptions_expose_only_two_read_tools(self):
        registry = create_document_tool_registry(self.queries)
        definitions = document_tool_definitions()
        self.assertEqual(set(registry), {"count_documents", "list_documents"})
        self.assertEqual({definition.name for definition in definitions}, set(registry))
        for definition in definitions:
            schema = definition.input_schema()
            self.assertFalse(schema["additionalProperties"])
            self.assertFalse(schema["properties"]["include_deleted"]["default"])
        schema = definitions[1].input_schema()
        self.assertEqual(schema["properties"]["limit"]["maximum"], 20)
        self.assertIn("incomplete", definitions[1].description)
        self.assertIn("subsequent turn", definitions[1].description)
        schema["properties"]["limit"]["maximum"] = 999
        self.assertEqual(definitions[1].input_schema()["properties"]["limit"]["maximum"], 20)

    def test_tool_modules_have_no_reverse_imports_dynamic_execution_or_clients(self):
        folder = Path(__file__).parents[1] / "app" / "tool_use"
        expected = {
            "__init__.py": set(), "contracts.py": set(),
            "executor.py": {"app.tool_use.contracts"},
        }
        for path in sorted(folder.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            internal = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app."):
                    internal.add(node.module)
                elif isinstance(node, ast.Import):
                    internal.update(alias.name for alias in node.names if alias.name.startswith("app."))
                elif isinstance(node, ast.Call):
                    name = ast.unparse(node.func)
                    self.assertNotIn(name, {"eval", "exec", "__import__", "MongoClient", "QdrantClient"})
            self.assertEqual(internal, expected[path.name])


class ToolExecutorTests(OfflineMixin, unittest.IsolatedAsyncioTestCase):
    def executor(self):
        return ToolExecutor(create_document_tool_registry(self.queries))

    async def test_count_tool_executes_successfully_in_a_worker(self):
        main_thread = threading.get_ident()
        worker_threads = []
        self.queries.count_hook = lambda: worker_threads.append(threading.get_ident())
        batch = await self.executor().execute([ToolCall("count-1", "count_documents", {})])
        self.assertTrue(batch.ok)
        self.assertEqual(batch.results[0].call_id, "count-1")
        self.assertEqual(batch.results[0].envelope["data"], self.queries.count_data)
        self.assertNotEqual(worker_threads, [main_thread])

    async def test_two_calls_are_sequential_and_results_keep_the_input_order(self):
        trace = []
        self.queries.list_hook = lambda: trace.append("list")
        def count_hook():
            self.assertEqual(trace, ["list"])
            trace.append("count")
        self.queries.count_hook = count_hook
        batch = await self.executor().execute([
            ToolCall("list-1", "list_documents", {}), ToolCall("count-1", "count_documents", {}),
        ])
        self.assertTrue(batch.ok)
        self.assertEqual(trace, ["list", "count"])
        self.assertEqual([result.call_id for result in batch.results], ["list-1", "count-1"])
        self.assertEqual(batch.results[0].envelope["data"], self.queries.list_data)

    async def test_unknown_tool_is_rejected_without_echoing_unknown_payload(self):
        batch = await self.executor().execute([ToolCall("x", "SENSITIVE_TOOL_NAME", {})])
        self.assertFalse(batch.ok)
        self.assert_error(batch.results[0].envelope, "TOOL_UNKNOWN")
        self.assertIsNone(batch.results[0].envelope["tool"])
        self.assertEqual(self.queries.calls, [])

    async def test_missing_blank_oversize_and_duplicate_call_ids_are_rejected(self):
        for calls in (
            [ToolCall(None, "count_documents", {})],
            [ToolCall("", "count_documents", {})],
            [ToolCall(" ", "count_documents", {})],
            [ToolCall("x" * 129, "count_documents", {})],
            [ToolCall("x", "count_documents", {}), ToolCall("x", "list_documents", {})],
        ):
            with self.subTest(calls=calls):
                batch = await self.executor().execute(calls)
                self.assertFalse(batch.ok)
                self.assert_error(batch.results[0].envelope, "TOOL_LIMIT_EXCEEDED")
        self.assertEqual(self.queries.calls, [])

    async def test_more_than_two_calls_and_empty_batch_are_rejected_before_execution(self):
        for calls in ([], [ToolCall(str(i), "count_documents", {}) for i in range(3)]):
            batch = await self.executor().execute(calls)
            self.assert_error(batch.results[0].envelope, "TOOL_LIMIT_EXCEEDED")
        self.assertEqual(self.queries.calls, [])

    async def test_invalid_batch_or_call_shapes_are_controlled(self):
        for calls in (None, {}, "SENSITIVE", [None], [{"id": "x"}]):
            batch = await self.executor().execute(calls)
            self.assertFalse(batch.ok)
            self.assertIsNone(batch.results[0].envelope["data"])
        self.assertEqual(self.queries.calls, [])

    async def test_validate_all_arguments_before_call_one_runs(self):
        for second in (
            ToolCall("b", "list_documents", {"limit": 21}),
            ToolCall("b", "analyze_document", {}),
            ToolCall("b", "count_documents", "{}" + " " * MAX_ARGUMENT_BYTES),
        ):
            batch = await self.executor().execute([ToolCall("a", "count_documents", {}), second])
            self.assertFalse(batch.ok)
            self.assertEqual(batch.results[0].call_id, "b")
        self.assertEqual(self.queries.calls, [])

    async def test_one_execute_attempt_consumes_the_only_round_even_after_validation_failure(self):
        for first_arguments in ({}, {"unknown": True}):
            with self.subTest(arguments=first_arguments):
                executor = self.executor()
                await executor.execute([ToolCall("a", "count_documents", first_arguments)])
                count = len(self.queries.calls)
                batch = await executor.execute([ToolCall("b", "count_documents", {})])
                self.assert_error(batch.results[0].envelope, "TOOL_LIMIT_EXCEEDED")
                self.assertEqual(len(self.queries.calls), count)

    async def test_query_failure_stops_batch_without_retry_or_empty_success(self):
        self.queries.error = RepositoryError("SENSITIVE_CONNECTION")
        batch = await self.executor().execute([
            ToolCall("a", "count_documents", {}), ToolCall("b", "list_documents", {}),
        ])
        self.assertFalse(batch.ok)
        self.assertEqual(len(batch.results), 1)
        self.assert_error(batch.results[0].envelope, "TOOL_QUERY_FAILED")
        self.assertEqual(self.queries.calls, [("count_documents", {"include_deleted": False})])

    async def test_second_call_failure_keeps_prefix_but_batch_is_not_success(self):
        def fail_list():
            raise RepositoryQueryTimeoutError("SENSITIVE_QUERY")
        self.queries.list_hook = fail_list
        batch = await self.executor().execute([
            ToolCall("a", "count_documents", {}), ToolCall("b", "list_documents", {}),
        ])
        self.assertFalse(batch.ok)
        self.assertTrue(batch.results[0].envelope["ok"])
        self.assert_error(batch.results[1].envelope, "TOOL_TIMEOUT")
        self.assertEqual([result.call_id for result in batch.results], ["a", "b"])
        self.assertEqual(len(self.queries.calls), 2)

    async def test_has_more_does_not_cause_automatic_pagination(self):
        batch = await self.executor().execute([ToolCall("a", "list_documents", {"offset": 0})])
        self.assertTrue(batch.ok)
        self.assertTrue(batch.results[0].envelope["data"]["has_more"])
        self.assertEqual(len(self.queries.calls), 1)

    async def test_registry_is_a_snapshot_and_rejects_unapproved_names(self):
        registry = create_document_tool_registry(self.queries)
        executor = ToolExecutor(registry)
        registry.clear()
        self.assertTrue((await executor.execute([ToolCall("a", "count_documents", {})])).ok)
        with self.assertRaises(ValueError):
            ToolExecutor({"analyze_document": lambda _: {}})
        with self.assertRaises(ValueError):
            ToolExecutor({"count_documents": None})

    async def test_async_handlers_are_rejected_instead_of_running_outside_sync_policy(self):
        async def handler(_arguments):
            self.fail("Async handler must not execute")
        class AsyncHandler:
            async def __call__(self, _arguments):
                self.fail("Async handler must not execute")
        for registered in (handler, AsyncHandler()):
            with self.assertRaises(ValueError):
                ToolExecutor({"count_documents": registered})
        # A sync callable returning a coroutine is also an invalid handler result.
        batch = await ToolExecutor({"count_documents": lambda arguments: handler(arguments)}).execute([
            ToolCall("a", "count_documents", {}),
        ])
        self.assert_error(batch.results[0].envelope, "TOOL_QUERY_FAILED")

    async def test_custom_handler_exception_or_invalid_result_is_safely_normalized(self):
        def explode(_arguments):
            raise RuntimeError("SENSITIVE_TRACE")
        for handler in (explode, lambda _: None, lambda _: {"SENSITIVE": True}):
            executor = ToolExecutor({"count_documents": handler})
            batch = await executor.execute([ToolCall("a", "count_documents", {})])
            self.assert_error(batch.results[0].envelope, "TOOL_QUERY_FAILED")

    async def test_exact_per_call_and_combined_result_byte_boundaries(self):
        def sized_handler(name, size):
            base = {"ok": True, "tool": name, "data": {"text": ""}, "error": None}
            empty_size = len(serialize_result(base).encode("utf-8"))
            base["data"]["text"] = "x" * (size - empty_size)
            return lambda _: deepcopy(base)
        registry = {name: sized_handler(name, MAX_RESULT_BYTES)
                    for name in ("count_documents", "list_documents")}
        batch = await ToolExecutor(registry).execute([
            ToolCall("a", "count_documents", {}), ToolCall("b", "list_documents", {}),
        ])
        self.assertTrue(batch.ok)
        self.assertEqual(sum(len(serialize_result(result.envelope).encode("utf-8"))
                             for result in batch.results), MAX_BATCH_RESULT_BYTES)
        registry["count_documents"] = sized_handler("count_documents", MAX_RESULT_BYTES + 1)
        failed = await ToolExecutor(registry).execute([ToolCall("c", "count_documents", {})])
        self.assert_error(failed.results[0].envelope, "TOOL_OUTPUT_LIMIT")

    async def test_aggregate_byte_budget_is_enforced_without_slicing_json(self):
        def handler(name):
            return lambda _: success_result(name, {"text": "x" * 250})
        executor = ToolExecutor({name: handler(name) for name in ("count_documents", "list_documents")})
        with patch("app.tool_use.executor.MAX_BATCH_RESULT_BYTES", 600):
            batch = await executor.execute([
                ToolCall("a", "count_documents", {}), ToolCall("b", "list_documents", {}),
            ])
        self.assertFalse(batch.ok)
        self.assert_error(batch.results[-1].envelope, "TOOL_OUTPUT_LIMIT")
        self.assertTrue(all(json.loads(serialize_result(result.envelope)) == result.envelope
                            for result in batch.results))
        self.assertLessEqual(sum(len(serialize_result(result.envelope).encode("utf-8"))
                                 for result in batch.results), 600)

    async def test_expired_deadline_never_starts_a_query(self):
        with patch("app.tool_use.executor.monotonic", return_value=100.0):
            batch = await self.executor().execute([ToolCall("a", "count_documents", {})], deadline=99.0)
        self.assert_error(batch.results[0].envelope, "TOOL_TIMEOUT")
        self.assertEqual(self.queries.calls, [])

    async def test_invalid_deadlines_are_controlled(self):
        for deadline in (True, "100", float("nan"), float("inf"), 10 ** 1000):
            batch = await self.executor().execute([ToolCall("a", "count_documents", {})], deadline=deadline)
            self.assert_error(batch.results[0].envelope, "TOOL_INVALID_ARGUMENTS")
        self.assertEqual(self.queries.calls, [])

    async def test_ten_second_stage_budget_is_not_reset_or_extended_by_parent_deadline(self):
        original_wait_for = asyncio.wait_for
        with patch("app.tool_use.executor.monotonic", side_effect=[100.0, 109.5, 109.5, 110.1]), \
                patch("app.tool_use.executor.asyncio.wait_for", wraps=original_wait_for) as wait:
            batch = await self.executor().execute([
                ToolCall("a", "count_documents", {}), ToolCall("b", "list_documents", {}),
            ], deadline=1000.0)
        self.assert_error(batch.results[0].envelope, "TOOL_TIMEOUT")
        self.assertEqual(wait.call_args.kwargs["timeout"], 0.5)
        self.assertEqual(len(self.queries.calls), 1)

    async def test_parent_deadline_can_shorten_the_five_second_call_budget(self):
        original_wait_for = asyncio.wait_for
        with patch("app.tool_use.executor.monotonic", return_value=100.0), \
                patch("app.tool_use.executor.asyncio.wait_for", wraps=original_wait_for) as wait:
            batch = await self.executor().execute([ToolCall("a", "count_documents", {})], deadline=101.0)
        self.assertTrue(batch.ok)
        self.assertEqual(wait.call_args.kwargs["timeout"], 1.0)

    async def test_timeout_stops_waiting_and_later_calls_but_does_not_claim_worker_stopped(self):
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        def block():
            started.set()
            try:
                release.wait(2)
            finally:
                finished.set()
        self.queries.count_hook = block
        try:
            with patch("app.tool_use.executor.MAX_TOOL_QUERY_SECONDS", 0.03):
                batch = await self.executor().execute([
                    ToolCall("a", "count_documents", {}), ToolCall("b", "list_documents", {}),
                ])
            self.assertTrue(started.is_set())
            self.assertFalse(finished.is_set())
            self.assert_error(batch.results[0].envelope, "TOOL_TIMEOUT")
            self.assertEqual(len(self.queries.calls), 1)
        finally:
            release.set()
            self.assertTrue(await asyncio.to_thread(finished.wait, 2))

    async def test_cancellation_propagates_without_scheduling_second_call_or_new_round(self):
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        def block():
            started.set()
            try:
                release.wait(2)
            finally:
                finished.set()
        self.queries.count_hook = block
        executor = self.executor()
        task = asyncio.create_task(executor.execute([
            ToolCall("a", "count_documents", {}), ToolCall("b", "list_documents", {}),
        ]))
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertFalse(finished.is_set())
            self.assertEqual(len(self.queries.calls), 1)
            rejected = await executor.execute([ToolCall("c", "count_documents", {})])
            self.assert_error(rejected.results[0].envelope, "TOOL_LIMIT_EXCEEDED")
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
            self.assertTrue(await asyncio.to_thread(finished.wait, 2))

    async def test_concurrent_execute_cannot_open_another_round(self):
        started, release = threading.Event(), threading.Event()
        def block():
            started.set()
            release.wait(2)
        self.queries.count_hook = block
        executor = self.executor()
        task = asyncio.create_task(executor.execute([ToolCall("a", "count_documents", {})]))
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            rejected = await executor.execute([ToolCall("b", "list_documents", {})])
            self.assert_error(rejected.results[0].envelope, "TOOL_LIMIT_EXCEEDED")
        finally:
            release.set()
            completed = await task
        self.assertTrue(completed.ok)
        self.assertEqual(len(self.queries.calls), 1)

    async def test_cancellation_raised_inside_handler_is_not_normalized_as_query_failure(self):
        self.queries.error = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.executor().execute([ToolCall("a", "count_documents", {})])


if __name__ == "__main__":
    unittest.main()
