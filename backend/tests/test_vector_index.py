"""Contract tests cho backend-neutral vector models và Qdrant adapter M-03."""

import unittest
from uuid import uuid4

from qdrant_client import QdrantClient

from app.infrastructure.qdrant_vector_index import QdrantVectorIndex
from app.rag.vector_index import (
    VectorConflictError,
    VectorFilter,
    VectorIndexError,
    VectorRecord,
    chunk_point_id,
)


class QdrantVectorIndexTests(unittest.TestCase):
    def setUp(self):
        self.client = QdrantClient(":memory:")
        self.index = QdrantVectorIndex(self.client, "m03_vectors")
        self.document_id = str(uuid4())
        self.version_id = str(uuid4())

    def tearDown(self):
        self.client.close()

    def record(
        self,
        *,
        chunk_index=0,
        text="alpha content",
        vector=(1.0, 0.0, 0.0),
        file_name="guide.md",
        version_id=None,
    ):
        resolved_version = version_id or self.version_id
        return VectorRecord(
            point_id=chunk_point_id(resolved_version, chunk_index),
            document_id=self.document_id,
            version_id=resolved_version,
            chunk_index=chunk_index,
            file_name=file_name,
            chunk_text=text,
            vector=vector,
            page=3,
        )

    def test_add_query_filter_upsert_count_and_delete(self):
        first = self.record()
        second_version = str(uuid4())
        second = self.record(
            version_id=second_version,
            text="beta content",
            vector=(0.0, 1.0, 0.0),
            file_name="other.md",
        )
        self.index.add([first, second])
        self.assertEqual(
            self.index.count(VectorFilter(document_id=self.document_id)), 2
        )

        by_version = self.index.query(
            [1.0, 0.0, 0.0],
            limit=5,
            filters=VectorFilter(
                document_id=self.document_id,
                version_id=self.version_id,
                file_name="guide.md",
            ),
        )
        self.assertEqual(len(by_version), 1)
        self.assertEqual(by_version[0].point_id, first.point_id)
        self.assertEqual(by_version[0].chunk_text, "alpha content")
        self.assertEqual(by_version[0].page, 3)

        by_active_versions = self.index.query(
            [1.0, 0.0, 0.0],
            limit=5,
            filters=VectorFilter(version_ids=(self.version_id, second_version)),
        )
        self.assertEqual({item.version_id for item in by_active_versions}, {
            self.version_id,
            second_version,
        })

        updated = self.record(text="updated content", vector=(0.5, 0.5, 0.0))
        self.index.upsert([updated])
        updated_result = self.index.query(
            [0.5, 0.5, 0.0],
            limit=1,
            filters=VectorFilter(version_id=self.version_id),
        )
        self.assertEqual(updated_result[0].chunk_text, "updated content")
        self.assertEqual(updated_result[0].point_id, first.point_id)

        self.index.delete(VectorFilter(version_id=self.version_id))
        self.assertEqual(self.index.count(VectorFilter(version_id=self.version_id)), 0)
        self.assertEqual(self.index.count(VectorFilter(document_id=self.document_id)), 1)
        self.index.delete(VectorFilter(document_id=self.document_id))
        self.assertEqual(self.index.count(VectorFilter(document_id=self.document_id)), 0)

    def test_add_rejects_existing_and_duplicate_point_ids(self):
        record = self.record()
        self.index.add([record])
        with self.assertRaises(VectorConflictError):
            self.index.add([record])
        with self.assertRaises(VectorConflictError):
            self.index.upsert([record, record])

    def test_value_objects_validate_ids_vectors_and_safe_delete_scope(self):
        with self.assertRaises(ValueError):
            VectorFilter(document_id="not-a-uuid")
        with self.assertRaises(ValueError):
            self.record(vector=(float("nan"), 1.0))
        with self.assertRaises(ValueError):
            self.index.delete(VectorFilter())

        versions = (str(uuid4()), str(uuid4()))
        self.assertEqual(VectorFilter(version_ids=versions).version_ids, versions)
        with self.assertRaises(ValueError):
            VectorFilter(version_id=versions[0], version_ids=versions)
        with self.assertRaises(ValueError):
            VectorFilter(version_ids=())
        with self.assertRaises(ValueError):
            self.index.query([], limit=1)
        with self.assertRaises(ValueError):
            self.index.query([1.0, 0.0, 0.0], limit=0)

    def test_backend_exception_is_wrapped_without_raw_detail(self):
        class FailingClient:
            def collection_exists(self, _name):
                raise RuntimeError("secret backend response")

        adapter = QdrantVectorIndex(FailingClient(), "safe_collection")
        with self.assertRaises(VectorIndexError) as raised:
            adapter.query([1.0], limit=1)
        self.assertNotIn("secret", str(raised.exception).lower())


if __name__ == "__main__":
    unittest.main()
