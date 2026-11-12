"""Unit tests for Advanced RAG Reranker implementations and integration."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from app.rag.reranker import (
    CohereReranker,
    FlashRankReranker,
    PassThroughReranker,
    RerankerPort,
    get_reranker,
)


class RerankerTests(unittest.TestCase):
    """Verify behavior of PassThrough, FlashRank, and factory reranker implementations."""

    def setUp(self) -> None:
        self.doc_apple = Document(
            page_content="Apples and oranges are delicious fruits rich in vitamin C.",
            metadata={"document_id": "doc-1", "chunk_id": "c1", "file_name": "fruits.txt"},
        )
        self.doc_vehicle = Document(
            page_content="Motorbikes and cars are road transport vehicles powered by fuel.",
            metadata={"document_id": "doc-2", "chunk_id": "c2", "file_name": "vehicles.txt"},
        )
        self.doc_capital = Document(
            page_content="Hanoi is the capital city of Vietnam.",
            metadata={"document_id": "doc-3", "chunk_id": "c3", "file_name": "geography.txt"},
        )

    def test_passthrough_reranker_preserves_order_and_bounds_top_k(self) -> None:
        reranker = PassThroughReranker()
        self.assertIsInstance(reranker, RerankerPort)

        docs = [self.doc_vehicle, self.doc_apple, self.doc_capital]
        result = reranker.rerank("Fruits and vitamins", docs, top_k=2)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].metadata["document_id"], "doc-2")
        self.assertEqual(result[1].metadata["document_id"], "doc-1")

    def test_passthrough_reranker_handles_empty_list(self) -> None:
        reranker = PassThroughReranker()
        self.assertEqual(reranker.rerank("any query", []), [])

    def test_flashrank_reranker_prioritizes_semantically_relevant_chunk(self) -> None:
        reranker = FlashRankReranker(model_name="ms-marco-TinyBERT-L-2-v2")
        self.assertIsInstance(reranker, RerankerPort)

        # Put doc_vehicle first, doc_apple second
        docs = [self.doc_vehicle, self.doc_apple, self.doc_capital]
        query = "Which fruits contain vitamins?"

        result = reranker.rerank(query, docs, top_k=2)

        # Doc apple must be re-ranked to the top
        self.assertGreaterEqual(len(result), 1)
        self.assertEqual(result[0].metadata["document_id"], "doc-1")
        self.assertIn("rerank_score", result[0].metadata)
        self.assertGreater(result[0].metadata["rerank_score"], 0.5)

    def test_flashrank_reranker_filters_below_relevance_threshold(self) -> None:
        reranker = FlashRankReranker(model_name="ms-marco-TinyBERT-L-2-v2")

        docs = [self.doc_apple, self.doc_vehicle]
        query = "Nutritional vitamins in fruits"

        # With a 0.5 threshold, doc_vehicle (score ~ 0.0) is filtered out while doc_apple is kept
        result = reranker.rerank(query, docs, relevance_threshold=0.5)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].metadata["document_id"], "doc-1")

    def test_flashrank_fallback_on_init_failure(self) -> None:
        reranker = FlashRankReranker(model_name="non-existent-model")
        with patch.object(reranker, "_get_ranker", return_value=None):
            docs = [self.doc_vehicle, self.doc_apple]
            result = reranker.rerank("Query", docs, top_k=1)
            # Khi model lỗi, fallback PassThrough an toàn
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].metadata["document_id"], "doc-2")

    def test_cohere_reranker_graceful_fallback_when_no_api_key(self) -> None:
        reranker = CohereReranker(api_key=None)
        with patch("app.shared.config.settings.cohere_api_key", None):
            docs = [self.doc_apple, self.doc_vehicle]
            result = reranker.rerank("Test query", docs, top_k=1)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].metadata["document_id"], "doc-1")

    def test_factory_get_reranker_respects_settings(self) -> None:
        # Khi enabled=False -> PassThroughReranker
        r1 = get_reranker(enabled=False)
        self.assertIsInstance(r1, PassThroughReranker)

        # Khi enabled=True, provider=flashrank -> FlashRankReranker
        r2 = get_reranker(enabled=True, provider="flashrank")
        self.assertIsInstance(r2, FlashRankReranker)

        # Khi provider không xác định -> PassThroughReranker an toàn
        r3 = get_reranker(enabled=True, provider="unknown_provider")
        self.assertIsInstance(r3, PassThroughReranker)


if __name__ == "__main__":
    unittest.main()
