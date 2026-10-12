"""Tests for Qdrant cutover retrieval and source mapping."""

import unittest
from uuid import uuid4

from langchain_core.embeddings import Embeddings

from app.rag.pipeline import _to_source
from app.rag.retriever import QdrantActiveVersionRetriever
from app.vector_index import VectorSearchResult


class FakeEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0]


class FakeRepository:
    def __init__(self, version_ids):
        self.version_ids = version_ids

    def list_active_version_ids(self):
        return list(self.version_ids)


class FakeVectorIndex:
    collection_name = "test"

    def __init__(self, result):
        self.result = result
        self.filters = None

    def query(self, query_vector, *, limit, filters=None):
        self.filters = filters
        return [self.result] if self.result.version_id in filters.version_ids else []


class QdrantRetrieverTests(unittest.TestCase):
    def setUp(self):
        self.document_id = str(uuid4())
        self.active_version_id = str(uuid4())
        self.result = VectorSearchResult(
            point_id=str(uuid4()),
            document_id=self.document_id,
            version_id=self.active_version_id,
            chunk_index=2,
            file_name="paper.pdf",
            chunk_text="Grounded active-version text",
            score=0.91,
            page=3,
        )

    def test_retrieval_uses_mongodb_active_version_filter_and_preserves_metadata(self):
        index = FakeVectorIndex(self.result)
        retriever = QdrantActiveVersionRetriever(
            vector_index=index,
            embeddings=FakeEmbeddings(),
            repository=FakeRepository((self.active_version_id,)),
            top_k=5,
        )

        documents = retriever.invoke("active content")

        self.assertEqual(len(documents), 1)
        self.assertEqual(index.filters.version_ids, (self.active_version_id,))
        self.assertEqual(documents[0].metadata["version_id"], self.active_version_id)
        self.assertEqual(documents[0].metadata["chunk_id"], self.result.point_id)
        self.assertEqual(documents[0].metadata["page"], 3)
        source = _to_source(documents[0])
        self.assertEqual(source["document_id"], self.document_id)
        self.assertEqual(source["version_id"], self.active_version_id)

    def test_no_active_versions_returns_no_results_without_vector_query(self):
        index = FakeVectorIndex(self.result)
        retriever = QdrantActiveVersionRetriever(
            vector_index=index,
            embeddings=FakeEmbeddings(),
            repository=FakeRepository(()),
        )

        self.assertEqual(retriever.invoke("anything"), [])
        self.assertIsNone(index.filters)

    def test_explicit_versions_isolate_evaluation_from_application_scope(self):
        eval_version = self.active_version_id
        retriever = QdrantActiveVersionRetriever(
            vector_index=FakeVectorIndex(self.result),
            embeddings=FakeEmbeddings(),
            active_version_ids=(eval_version,),
            repository=FakeRepository((str(uuid4()),)),
        )

        documents = retriever.invoke("eval")

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].metadata["version_id"], eval_version)


if __name__ == "__main__":
    unittest.main()
