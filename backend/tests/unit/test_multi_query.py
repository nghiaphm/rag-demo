"""Unit tests for Multi-Query Expansion in RAG pipeline."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from langchain_core.documents import Document
from langchain_core.messages import AIMessage

from app.chat.multi_query import MultiQueryExpander, create_multi_query_expander
from app.chat.pipeline import _retrieve_for_queries, prepare_rag_request_from_components
from app.conversations.history import HistoryTurn
from app.rag.reranker import PassThroughReranker


class MultiQueryExpansionTests(unittest.IsolatedAsyncioTestCase):
    async def test_expand_disabled_returns_original_query_only(self):
        expander = MultiQueryExpander(enabled=False)
        queries = await expander.expand("Làm thế nào để cấu hình RAG?")
        self.assertEqual(queries, ["Làm thế nào để cấu hình RAG?"])

    async def test_expand_enabled_invokes_llm_and_parses_variations(self):
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(
                content=(
                    "1. Hướng dẫn thiết lập hệ thống RAG\n"
                    "2. Các bước cấu hình RAG pipeline\n"
                    "- Cách thức triển khai retrieval augmented generation\n"
                )
            )
        )
        expander = MultiQueryExpander(enabled=True, count=3, llm=mock_llm)
        queries = await expander.expand("Làm thế nào để cấu hình RAG?")

        self.assertEqual(len(queries), 4)  # original + 3 variations
        self.assertEqual(queries[0], "Làm thế nào để cấu hình RAG?")
        self.assertIn("Hướng dẫn thiết lập hệ thống RAG", queries)
        self.assertIn("Các bước cấu hình RAG pipeline", queries)
        self.assertIn("Cách thức triển khai retrieval augmented generation", queries)

    async def test_expand_handles_timeout_gracefully(self):
        mock_llm = MagicMock()
        async def slow_invoke(*args, **kwargs):
            await asyncio.sleep(0.5)
            return AIMessage(content="variation")
        mock_llm.ainvoke = slow_invoke

        expander = MultiQueryExpander(enabled=True, timeout_seconds=0.01, llm=mock_llm)
        queries = await expander.expand("Câu hỏi gốc")
        self.assertEqual(queries, ["Câu hỏi gốc"])

    async def test_retrieve_for_queries_merges_and_deduplicates_documents(self):
        doc_id = str(uuid4())
        version_id = str(uuid4())
        chunk1 = Document(
            page_content="Nội dung chunk 1",
            metadata={"chunk_id": str(uuid4()), "document_id": doc_id, "version_id": version_id, "chunk_index": 0},
        )
        chunk2 = Document(
            page_content="Nội dung chunk 2",
            metadata={"chunk_id": str(uuid4()), "document_id": doc_id, "version_id": version_id, "chunk_index": 1},
        )
        chunk3 = Document(
            page_content="Nội dung chunk 3",
            metadata={"chunk_id": str(uuid4()), "document_id": doc_id, "version_id": version_id, "chunk_index": 2},
        )

        mock_retriever = MagicMock()
        # Query 1 trả về [chunk1, chunk2]
        # Query 2 trả về [chunk2, chunk3] (chunk2 bị lặp)
        mock_retriever.invoke.side_effect = lambda q: [chunk1, chunk2] if "1" in q else [chunk2, chunk3]

        results = await _retrieve_for_queries(mock_retriever, ["query 1", "query 2"])

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].page_content, "Nội dung chunk 1")
        self.assertEqual(results[1].page_content, "Nội dung chunk 2")
        self.assertEqual(results[2].page_content, "Nội dung chunk 3")

    async def test_pipeline_integrates_multi_query_and_reranker(self):
        version_id = str(uuid4())
        doc1 = Document(
            page_content="Tài liệu A",
            metadata={"chunk_id": str(uuid4()), "document_id": str(uuid4()), "version_id": version_id, "chunk_index": 0, "file_name": "a.txt"},
        )
        doc2 = Document(
            page_content="Tài liệu B",
            metadata={"chunk_id": str(uuid4()), "document_id": str(uuid4()), "version_id": version_id, "chunk_index": 1, "file_name": "b.txt"},
        )

        mock_retriever = MagicMock()
        mock_retriever.invoke.side_effect = lambda q: [doc1] if "a" in q else [doc2]

        mock_expander = MagicMock()
        mock_expander.expand = AsyncMock(return_value=["query a", "query b"])

        prepared = await prepare_rag_request_from_components(
            "Tìm tài liệu",
            history_turns=(),
            active_version_ids=(version_id,),
            retriever=mock_retriever,
            reranker=PassThroughReranker(),
            multi_query_expander=mock_expander,
        )

        # Cả doc1 và doc2 đều được retrieve từ 2 queries và đưa vào context
        self.assertEqual(len(prepared.sources), 2)
        mock_expander.expand.assert_awaited_once()
