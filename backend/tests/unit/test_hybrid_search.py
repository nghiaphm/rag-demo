"""Unit tests for Advanced RAG Phase 2: Hybrid Search (Dense + Keyword BM25 with RRF)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from qdrant_client import QdrantClient
from langchain_core.documents import Document

from app.infrastructure.qdrant_vector_index import QdrantVectorIndex
from app.rag.retriever import QdrantActiveVersionRetriever
from app.rag.vector_index import VectorFilter, VectorRecord, VectorSearchResult


class HybridSearchTests(unittest.TestCase):
    """Verify QdrantVectorIndex hybrid search and retriever integration."""

    def setUp(self) -> None:
        self.client = QdrantClient(":memory:")
        self.collection_name = "test_hybrid_collection"
        self.index = QdrantVectorIndex(self.client, self.collection_name)

        # 3 points:
        # Point 1 has unique code "DOC-CODE-999" (exact keyword), vector [0.1, 0.9, 0.0, 0.0]
        # Point 2 has semantic text "Xe hoi va o to", vector [0.9, 0.1, 0.0, 0.0]
        # Point 3 is irrelevant "Hoc ngoai ngu online", vector [0.0, 0.0, 0.9, 0.1]
        self.records = [
            VectorRecord(
                point_id="11111111-1111-4111-8111-111111111111",
                document_id="22222222-2222-4222-8222-222222222222",
                version_id="33333333-3333-4333-8333-333333333333",
                chunk_index=0,
                file_name="spec.txt",
                chunk_text="Quy trinh dac ta ma hieu DOC-CODE-999 duoc phe duyet.",
                vector=(0.1, 0.9, 0.0, 0.0),
            ),
            VectorRecord(
                point_id="44444444-4444-4444-8444-444444444444",
                document_id="55555555-5555-4555-8555-555555555555",
                version_id="33333333-3333-4333-8333-333333333333",
                chunk_index=0,
                file_name="vehicle.txt",
                chunk_text="Xe hoi va o to la cac phuong tien giao thong pho bien.",
                vector=(0.9, 0.1, 0.0, 0.0),
            ),
            VectorRecord(
                point_id="77777777-7777-4777-8777-777777777777",
                document_id="88888888-8888-4888-8888-888888888888",
                version_id="33333333-3333-4333-8333-333333333333",
                chunk_index=0,
                file_name="study.txt",
                chunk_text="Hoc ngoai ngu online giup cai thien ky nang giao tiep.",
                vector=(0.0, 0.0, 0.9, 0.1),
            ),
        ]
        self.index.add(self.records)

    def test_query_hybrid_fuses_dense_and_keyword_hits(self) -> None:
        # Query: "xe hoi DOC-CODE-999"
        # Query vector is aligned with Point 2 (vehicle)
        query_vector = (0.9, 0.1, 0.0, 0.0)
        query_text = "xe hoi DOC-CODE-999"

        results = self.index.query_hybrid(
            query_text=query_text,
            query_vector=query_vector,
            limit=2,
            filters=VectorFilter(version_id="33333333-3333-4333-8333-333333333333"),
        )

        self.assertEqual(len(results), 2)
        # Point 1 (DOC-CODE-999 via keyword) and Point 2 (xe hoi via dense + keyword)
        result_ids = {r.point_id for r in results}
        self.assertIn("11111111-1111-4111-8111-111111111111", result_ids)
        self.assertIn("44444444-4444-4444-8444-444444444444", result_ids)

    def test_query_hybrid_pure_dense_fallback_when_keyword_yields_nothing(self) -> None:
        # Keyword "xyz123nonsense" has no match, but query_vector matches Point 2
        query_vector = (0.9, 0.1, 0.0, 0.0)
        results = self.index.query_hybrid(
            query_text="xyz123nonsense",
            query_vector=query_vector,
            limit=1,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].point_id, "44444444-4444-4444-8444-444444444444")

    def test_retriever_dispatches_to_query_hybrid_when_enabled(self) -> None:
        mock_index = MagicMock()
        mock_index.query_hybrid.return_value = [
            VectorSearchResult(
                point_id="11111111-1111-4111-8111-111111111111",
                document_id="22222222-2222-4222-8222-222222222222",
                version_id="33333333-3333-4333-8333-333333333333",
                chunk_index=0,
                file_name="spec.txt",
                chunk_text="Sample text",
                score=0.95,
            )
        ]
        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1, 0.2, 0.3, 0.4]

        retriever = QdrantActiveVersionRetriever(
            vector_index=mock_index,
            embeddings=mock_embeddings,
            active_version_ids=("33333333-3333-4333-8333-333333333333",),
            top_k=3,
        )

        with patch("app.rag.retriever.settings.hybrid_search_enabled", True):
            docs = retriever.invoke("tim kiem ma hieu DOC-CODE-999")
            self.assertEqual(len(docs), 1)
            mock_index.query_hybrid.assert_called_once()
            mock_index.query.assert_not_called()

    def test_retriever_dispatches_to_query_when_hybrid_disabled(self) -> None:
        mock_index = MagicMock()
        mock_index.query.return_value = []
        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1, 0.2, 0.3, 0.4]

        retriever = QdrantActiveVersionRetriever(
            vector_index=mock_index,
            embeddings=mock_embeddings,
            active_version_ids=("33333333-3333-4333-8333-333333333333",),
            top_k=3,
        )

        with patch("app.rag.retriever.settings.hybrid_search_enabled", False):
            docs = retriever.invoke("cau hoi thong thuong")
            mock_index.query.assert_called_once()
            mock_index.query_hybrid.assert_not_called()


if __name__ == "__main__":
    unittest.main()
