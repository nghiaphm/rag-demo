"""Offline tests of the real Documents repository/facade with deterministic I/O."""

import inspect
import json
import socket
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID

from pymongo.errors import ExecutionTimeout, NetworkTimeout, OperationFailure

from app.documents.indexes import (
    DOCUMENTS_COLLECTION,
    DOCUMENT_VERSIONS_COLLECTION,
    INGESTION_JOBS_COLLECTION,
)
from app.documents.models import DocumentRecord, DocumentStatus
from app.documents.queries import (
    MAX_DOCUMENT_LIST_RESULT_BYTES,
    DocumentQueries,
    DocumentQueryOutputLimitError,
)
from app.documents.repository import (
    DOCUMENT_QUERY_MAX_OFFSET,
    DocumentQueryParameterError,
    MongoDocumentRepository,
    RepositoryError,
    RepositoryQueryTimeoutError,
)

STAMP = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


def document(index, *, file_name=None, status=DocumentStatus.INDEXED, **values):
    return DocumentRecord(
        document_id=str(UUID(int=index + 1)),
        file_name=file_name or f"document-{index}.md",
        active_version_id=str(UUID(int=index + 100)),
        status=status,
        created_at=values.pop("created_at", STAMP),
        updated_at=values.pop("updated_at", STAMP),
        **values,
    ).to_mongo()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class Cursor:
    """Apply the query/order/skip/limit requested by the production repository."""

    def __init__(self, collection, query):
        self.collection = collection
        self.query = query
        self.order = []
        self.offset = 0
        self.bound = None
        self.timeout_ms = None
        self.closed = False

    def sort(self, keys, direction=None):
        self.order = [(keys, direction)] if isinstance(keys, str) else keys
        return self

    def skip(self, offset):
        self.offset = offset
        return self

    def limit(self, limit):
        self.bound = limit
        return self

    def max_time_ms(self, value):
        self.timeout_ms = value
        return self

    def __iter__(self):
        if self.collection.iteration_error:
            raise self.collection.iteration_error
        values = deepcopy([
            value for value in self.collection.values
            if self.collection.matches(value, self.query)
        ])
        for key, direction in reversed(self.order):
            values.sort(key=lambda value: value[key], reverse=direction < 0)
        values = values[self.offset:]
        return iter(values if self.bound is None else values[:self.bound])

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.closed = True


class Collection:
    def __init__(self, values=()):
        self.values = deepcopy(list(values))
        self.count_calls = []
        self.find_calls = []
        self.cursors = []
        self.count_error = None
        self.find_error = None
        self.iteration_error = None

    @staticmethod
    def matches(value, query):
        return all(
            value.get(key) != expected["$ne"] if isinstance(expected, dict)
            else value.get(key) == expected
            for key, expected in query.items()
        )

    def count_documents(self, query, **options):
        self.count_calls.append((deepcopy(query), options))
        if self.count_error:
            raise self.count_error
        return sum(self.matches(value, query) for value in self.values)

    def find(self, query):
        self.find_calls.append(deepcopy(query))
        if self.find_error:
            raise self.find_error
        cursor = Cursor(self, query)
        self.cursors.append(cursor)
        return cursor


class DocumentQueryTests(unittest.TestCase):
    def setUp(self):
        # Any accidental network access fails this suite, even if code catches it.
        network = patch.object(socket.socket, "connect", side_effect=AssertionError("offline only"))
        self.connect = network.start()
        self.addCleanup(network.stop)

    def tearDown(self):
        self.connect.assert_not_called()

    def fixture(self, values=(), *, versions=()):
        documents = Collection(values)
        self.versions = Collection(versions)
        self.jobs = Collection()
        repository = MongoDocumentRepository({
            DOCUMENTS_COLLECTION: documents,
            DOCUMENT_VERSIONS_COLLECTION: self.versions,
            INGESTION_JOBS_COLLECTION: self.jobs,
        })
        return documents, repository, DocumentQueries(repository)

    def assert_no_query(self, collection):
        self.assertEqual(collection.count_calls, [])
        self.assertEqual(collection.find_calls, [])

    def test_six_active_documents_have_exact_count_and_six_items(self):
        collection, _, queries = self.fixture(document(i) for i in range(6))
        self.assertEqual(queries.count_documents(), {
            "count": 6, "unit": "document", "scope": "library", "include_deleted": False,
        })
        page = queries.list_documents()
        self.assertEqual(page["returned_count"], 6)
        self.assertEqual(len(page["items"]), 6)
        self.assertFalse(page["has_more"])
        self.assertIsNone(page["next_offset"])
        self.assertEqual(collection.count_calls, [
            ({"status": {"$ne": "DELETED"}}, {"maxTimeMS": 5000}),
        ])

    def test_deleted_default_and_all_nondeleted_statuses_share_one_predicate(self):
        values = [document(i, status=status) for i, status in enumerate(DocumentStatus)]
        collection, _, queries = self.fixture(values)
        self.assertEqual(queries.count_documents()["count"], 4)
        page = queries.list_documents()
        self.assertEqual({item["status"] for item in page["items"]}, {
            "UPLOADED", "PROCESSING", "INDEXED", "FAILED",
        })
        self.assertEqual(collection.find_calls[-1], collection.count_calls[-1][0])

    def test_include_deleted_true_includes_deleted_in_count_and_list(self):
        collection, _, queries = self.fixture([
            document(0), document(1, status=DocumentStatus.DELETED),
        ])
        self.assertEqual(queries.count_documents(include_deleted=True)["count"], 2)
        page = queries.list_documents(include_deleted=True)
        self.assertEqual(page["returned_count"], 2)
        self.assertTrue(page["include_deleted"])
        self.assertEqual(collection.count_calls[-1][0], {})
        self.assertEqual(collection.find_calls[-1], {})

    def test_visibility_uses_status_not_deleted_timestamp_or_active_pointer(self):
        values = [
            document(0, status=DocumentStatus.FAILED, deleted_at=STAMP),
            document(1, status=DocumentStatus.DELETED, deleted_at=None),
        ]
        values[0]["active_version_id"] = None
        _, _, queries = self.fixture(values)
        self.assertEqual(queries.count_documents()["count"], 1)
        self.assertEqual(queries.list_documents()["items"][0]["document_id"], values[0]["_id"])

    def test_multiple_versions_and_jobs_are_not_counted_or_queried(self):
        value = document(0)
        _, _, queries = self.fixture([value], versions=[
            {"document_id": value["_id"], "version": i, "chunk_count": 100}
            for i in range(1, 4)
        ])
        self.assertEqual(queries.count_documents()["count"], 1)
        self.assertEqual(queries.list_documents()["returned_count"], 1)
        self.assert_no_query(self.versions)
        self.assert_no_query(self.jobs)

    def test_duplicate_filenames_remain_separate_identities(self):
        _, _, queries = self.fixture([document(i, file_name="same.md") for i in range(2)])
        self.assertEqual(queries.count_documents()["count"], 2)
        items = queries.list_documents()["items"]
        self.assertEqual(len({item["document_id"] for item in items}), 2)
        self.assertEqual([item["file_name"] for item in items], ["same.md", "same.md"])

    def test_timestamp_ties_are_ordered_by_descending_identity(self):
        expected = [str(UUID(int=i + 1)) for i in reversed(range(6))]
        for permutation in ([0, 5, 2, 4, 1, 3], [5, 4, 3, 2, 1, 0]):
            with self.subTest(permutation=permutation):
                _, _, queries = self.fixture(document(i) for i in permutation)
                self.assertEqual([
                    item["document_id"] for item in queries.list_documents()["items"]
                ], expected)

    def test_creation_time_is_the_primary_sort_key(self):
        _, _, queries = self.fixture([
            document(0), document(99, created_at=STAMP - timedelta(days=1)),
        ])
        self.assertEqual([
            item["document_id"] for item in queries.list_documents()["items"]
        ], [str(UUID(int=1)), str(UUID(int=100))])

    def test_empty_library_and_offset_beyond_end_are_valid_empty_pages(self):
        for values, offset in (([], 0), ([document(0)], 1), ([document(0)], 100)):
            with self.subTest(offset=offset, size=len(values)):
                _, _, queries = self.fixture(values)
                page = queries.list_documents(offset=offset)
                self.assertEqual(page, {
                    "items": [], "scope": "library", "include_deleted": False,
                    "offset": offset, "limit": 10, "returned_count": 0,
                    "has_more": False, "next_offset": None, "truncated_by_bytes": False,
                    "order": ["created_at:desc", "document_id:desc"],
                })
                if not values:
                    self.assertEqual(queries.count_documents()["count"], 0)

    def test_sentinel_pages_have_no_missing_or_duplicate_identities(self):
        values = [document(i) for i in range(25)]
        collection, _, queries = self.fixture(values)
        first = queries.list_documents(limit=20)
        self.assertEqual(first["returned_count"], 20)
        self.assertEqual(first["next_offset"], 20)
        self.assertTrue(first["has_more"])
        self.assertFalse(first["truncated_by_bytes"])
        self.assertEqual(collection.cursors[-1].bound, 21)
        second = queries.list_documents(offset=first["next_offset"], limit=20)
        self.assertEqual(second["returned_count"], 5)
        self.assertFalse(second["has_more"])
        self.assertIsNone(second["next_offset"])
        self.assertEqual([
            item["document_id"] for item in first["items"] + second["items"]
        ], [value["_id"] for value in reversed(values)])

    def test_default_and_minimum_page_limits_fetch_one_extra(self):
        collection, _, queries = self.fixture(document(i) for i in range(12))
        self.assertEqual(queries.list_documents()["returned_count"], 10)
        self.assertEqual(collection.cursors[-1].bound, 11)
        page = queries.list_documents(limit=1)
        self.assertEqual(page["returned_count"], 1)
        self.assertEqual(page["next_offset"], 1)
        self.assertEqual(collection.cursors[-1].bound, 2)

    def test_repository_allows_21_item_fetch_but_facade_returns_at_most_20(self):
        collection, repository, queries = self.fixture(document(i) for i in range(30))
        self.assertEqual(len(repository.list_documents_for_tools()), 21)
        self.assertEqual(queries.list_documents(limit=20)["returned_count"], 20)
        with self.assertRaises(DocumentQueryParameterError):
            queries.list_documents(limit=21)
        self.assertEqual(len(collection.find_calls), 2)

    def test_include_deleted_rejects_coercions_before_database_access(self):
        collection, repository, queries = self.fixture()
        for value in (None, 0, 1, "false", [], {}):
            for target in (
                repository.count_documents_for_tools, repository.list_documents_for_tools,
                queries.count_documents, queries.list_documents,
            ):
                with self.subTest(value=value, target=target.__name__):
                    with self.assertRaises(DocumentQueryParameterError):
                        target(include_deleted=value)
        self.assert_no_query(collection)

    def test_offset_rejects_negative_coercions_and_int64_overflow(self):
        collection, repository, queries = self.fixture()
        for value in (-1, True, False, 1.5, "1", None, DOCUMENT_QUERY_MAX_OFFSET + 1):
            for target in (repository.list_documents_for_tools, queries.list_documents):
                with self.subTest(value=value, target=target.__name__):
                    with self.assertRaises(DocumentQueryParameterError):
                        target(offset=value)
        self.assert_no_query(collection)

    def test_maximum_int64_skip_is_accepted_without_overflow(self):
        collection, _, queries = self.fixture()
        page = queries.list_documents(offset=DOCUMENT_QUERY_MAX_OFFSET)
        self.assertEqual(page["items"], [])
        self.assertIsNone(page["next_offset"])
        self.assertEqual(collection.cursors[-1].offset, DOCUMENT_QUERY_MAX_OFFSET)

    def test_invalid_limit_is_rejected_before_database_access(self):
        collection, repository, queries = self.fixture()
        for target, maximum in ((repository.list_documents_for_tools, 21), (queries.list_documents, 20)):
            for value in (0, -1, maximum + 1, True, False, 1.5, "10", None):
                with self.subTest(value=value, target=target.__name__):
                    with self.assertRaises(DocumentQueryParameterError):
                        target(limit=value)
        self.assert_no_query(collection)

    def test_query_timeouts_are_server_controlled_and_bounded(self):
        collection, repository, queries = self.fixture()
        for value in (0, -1, 5001, True, 1.5, "5000", None):
            for target in (repository.count_documents_for_tools, repository.list_documents_for_tools):
                with self.subTest(value=value, target=target.__name__):
                    with self.assertRaises(DocumentQueryParameterError):
                        target(max_time_ms=value)
        self.assert_no_query(collection)
        self.assertNotIn("max_time_ms", inspect.signature(queries.count_documents).parameters)
        self.assertNotIn("max_time_ms", inspect.signature(queries.list_documents).parameters)
        repository.count_documents_for_tools(max_time_ms=1)
        repository.list_documents_for_tools(max_time_ms=1250)
        self.assertEqual(collection.count_calls[-1][1], {"maxTimeMS": 1})
        self.assertEqual(collection.cursors[-1].timeout_ms, 1250)
        queries.list_documents()
        self.assertEqual(collection.cursors[-1].timeout_ms, 5000)

    def test_count_database_failure_is_safely_wrapped(self):
        collection, _, queries = self.fixture()
        collection.count_error = OperationFailure("SENSITIVE_DB_DETAILS", code=123)
        with self.assertRaises(RepositoryError) as raised:
            queries.count_documents()
        self.assertNotIsInstance(raised.exception, RepositoryQueryTimeoutError)
        self.assertNotIn("SENSITIVE", str(raised.exception))
        self.assertTrue(raised.exception.__suppress_context__)

    def test_count_execution_and_network_timeouts_are_controlled(self):
        for error in (ExecutionTimeout("SENSITIVE", code=50), NetworkTimeout("SENSITIVE")):
            with self.subTest(error=type(error).__name__):
                collection, _, queries = self.fixture()
                collection.count_error = error
                with self.assertRaises(RepositoryQueryTimeoutError) as raised:
                    queries.count_documents()
                self.assertNotIn("SENSITIVE", str(raised.exception))

    def test_list_find_failure_and_lazy_iteration_failure_are_safely_wrapped(self):
        for stage in ("find_error", "iteration_error"):
            with self.subTest(stage=stage):
                collection, _, queries = self.fixture([document(0)])
                setattr(collection, stage, OperationFailure("SENSITIVE_DB_DETAILS", code=123))
                with self.assertRaises(RepositoryError) as raised:
                    queries.list_documents()
                self.assertNotIn("SENSITIVE", str(raised.exception))
                if stage == "iteration_error":
                    self.assertTrue(collection.cursors[-1].closed)

    def test_list_timeouts_are_controlled_and_cursor_is_closed(self):
        for error in (ExecutionTimeout("SENSITIVE", code=50), NetworkTimeout("SENSITIVE")):
            with self.subTest(error=type(error).__name__):
                collection, _, queries = self.fixture([document(0)])
                collection.iteration_error = error
                with self.assertRaises(RepositoryQueryTimeoutError) as raised:
                    queries.list_documents()
                self.assertNotIn("SENSITIVE", str(raised.exception))
                self.assertTrue(collection.cursors[-1].closed)

    def test_malformed_stored_metadata_is_controlled_not_a_raw_validation_error(self):
        for invalid in (
            {"_id": "SENSITIVE_INVALID_UUID"}, {"status": "SENSITIVE_INVALID_STATUS"},
            {"file_name": None}, {"created_at": datetime(2026, 10, 30)},
        ):
            with self.subTest(invalid=invalid):
                value = document(0)
                value.update(invalid)
                collection, _, queries = self.fixture([value])
                with self.assertRaises(RepositoryError) as raised:
                    queries.list_documents()
                self.assertEqual(str(raised.exception), "Document metadata không hợp lệ")
                self.assertTrue(raised.exception.__suppress_context__)
                self.assertTrue(collection.cursors[-1].closed)

    def test_invalid_sentinel_metadata_is_not_silently_accepted(self):
        values = [document(i) for i in range(21)]
        values[0]["file_name"] = None  # Oldest ID is the sentinel, not a returned item.
        _, _, queries = self.fixture(values)
        with self.assertRaises(RepositoryError):
            queries.list_documents(limit=20)

    def test_safe_projection_has_only_approved_fields_and_utc_timestamps(self):
        local = STAMP.astimezone(timezone(timedelta(hours=7)))
        value = document(0, created_at=local, updated_at=local, source_key="PRIVATE_SOURCE")
        _, _, queries = self.fixture([value])
        item = queries.list_documents()["items"][0]
        self.assertEqual(set(item), {
            "document_id", "file_name", "status", "active_version_id", "created_at", "updated_at",
        })
        self.assertEqual(item["created_at"], "2026-10-30T12:00:00+00:00")
        self.assertEqual(item["updated_at"], item["created_at"])
        self.assertNotIn("PRIVATE_SOURCE", encoded(item).decode())

    def test_utf8_byte_truncation_preserves_filenames_and_pagination_across_pages(self):
        name = "😀" * 251 + ".md"
        values = [document(i, file_name=name) for i in range(25)]
        _, _, queries = self.fixture(values)
        seen, offset = [], 0
        for _ in range(25):
            page = queries.list_documents(offset=offset, limit=20)
            self.assertLessEqual(len(encoded(page)), MAX_DOCUMENT_LIST_RESULT_BYTES)
            # Reserve also protects the approved future wrapper without implementing tools.
            self.assertLessEqual(len(encoded({
                "ok": True, "tool": "list_documents", "data": page, "error": None,
            })), MAX_DOCUMENT_LIST_RESULT_BYTES)
            self.assertEqual(page["returned_count"], len(page["items"]))
            self.assertTrue(all(item["file_name"] == name for item in page["items"]))
            seen.extend(item["document_id"] for item in page["items"])
            if not page["has_more"]:
                self.assertIsNone(page["next_offset"])
                break
            self.assertTrue(page["truncated_by_bytes"])
            self.assertGreater(page["returned_count"], 0)
            self.assertEqual(page["next_offset"], offset + page["returned_count"])
            offset = page["next_offset"]
        else:
            self.fail("Pagination failed to make progress")
        self.assertEqual(seen, [value["_id"] for value in reversed(values)])

    def test_byte_truncation_sets_has_more_even_without_a_sentinel(self):
        _, _, queries = self.fixture(document(i, file_name="😀" * 255) for i in range(20))
        page = queries.list_documents(limit=20)
        self.assertLess(page["returned_count"], 20)
        self.assertTrue(page["truncated_by_bytes"])
        self.assertTrue(page["has_more"])
        self.assertEqual(page["next_offset"], page["returned_count"])

    def test_a_complete_item_that_cannot_fit_raises_output_limit(self):
        _, _, queries = self.fixture([document(0)])
        with patch("app.documents.queries.MAX_DOCUMENT_LIST_RESULT_BYTES", 64):
            with self.assertRaises(DocumentQueryOutputLimitError):
                queries.list_documents()

    def test_unencodable_filename_does_not_leak_unicode_exception(self):
        value = document(0)
        value["file_name"] = "bad-\ud800.md"
        _, _, queries = self.fixture([value])
        with self.assertRaises(RepositoryError) as raised:
            queries.list_documents()
        self.assertNotIsInstance(raised.exception, UnicodeError)
        self.assertTrue(raised.exception.__suppress_context__)

    def test_existing_list_signature_and_query_order_are_unchanged(self):
        collection, repository, _ = self.fixture([
            document(0), document(1, status=DocumentStatus.DELETED), document(2),
        ])
        parameters = inspect.signature(repository.list_documents).parameters
        self.assertEqual(list(parameters), ["include_deleted", "offset", "limit"])
        self.assertEqual([parameter.default for parameter in parameters.values()], [False, 0, 100])
        values = repository.list_documents(include_deleted=True, offset=1, limit=1)
        self.assertEqual(len(values), 1)
        self.assertEqual(collection.find_calls[-1], {})
        cursor = collection.cursors[-1]
        self.assertEqual(cursor.order, [("created_at", -1)])
        self.assertEqual((cursor.offset, cursor.bound, cursor.timeout_ms), (1, 1, None))
        values = repository.list_documents()
        self.assertEqual(len(values), 2)
        self.assertEqual(collection.find_calls[-1], {"status": {"$ne": "DELETED"}})


if __name__ == "__main__":
    unittest.main()
