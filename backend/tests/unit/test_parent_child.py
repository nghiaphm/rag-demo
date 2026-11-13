"""Unit tests for Parent-Child (Hierarchical) Chunking and Retrieval."""

import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.rag.indexing import build_vector_records
from app.rag.retriever import QdrantActiveVersionRetriever
from app.rag.splitter import split_documents, split_parent_child
from app.rag.vector_index import VectorSearchResult
from app.shared.config import settings


class FakeEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0]


class ParentChildChunkingTests(unittest.TestCase):
    def test_split_parent_child_produces_child_chunks_with_parent_reference(self):
        text = (
            "Giới thiệu RAG nâng cao. Hệ thống RAG này sử dụng kiến trúc hai tầng. "
            "Tầng thứ nhất là Parent-Child Chunking. Tầng thứ hai là Hybrid Search và Reranker. "
            "Toàn bộ tài liệu được phân tách một cách phân cấp nhằm đảm bảo chất lượng ngữ cảnh."
        )
        doc = Document(page_content=text, metadata={"document_id": str(uuid4()), "version_id": str(uuid4())})

        children = split_parent_child(
            [doc],
            parent_size=100,
            parent_overlap=20,
            child_size=40,
            child_overlap=10,
        )

        self.assertGreater(len(children), 1)
        for child in children:
            self.assertIn("parent_id", child.metadata)
            self.assertIn("parent_text", child.metadata)
            self.assertIn("parent_index", child.metadata)
            self.assertIn("child_index", child.metadata)
            self.assertTrue(len(child.page_content) <= 40)
            self.assertIn(child.page_content, child.metadata["parent_text"])

    def test_split_documents_dispatches_to_parent_child_when_flag_enabled(self):
        text = "Một đoạn văn bản mẫu để kiểm tra dispatching tới parent-child chunking."
        doc = Document(page_content=text, metadata={"version_id": str(uuid4())})

        with patch.object(settings, "parent_child_enabled", True):
            chunks = split_documents([doc])
            self.assertGreater(len(chunks), 0)
            self.assertIn("parent_id", chunks[0].metadata)

    def test_build_vector_records_preserves_parent_fields_in_payload(self):
        doc_id = str(uuid4())
        version_id = str(uuid4())
        parent_id = str(uuid4())
        parent_text = "Nội dung đoạn cha đầy đủ ngữ cảnh"

        child_doc = Document(
            page_content="Nội dung con",
            metadata={
                "parent_id": parent_id,
                "parent_text": parent_text,
                "page": 1,
            },
        )
        records = build_vector_records(
            document_id=doc_id,
            version_id=version_id,
            file_name="test.pdf",
            chunks=[child_doc],
            vectors=[[0.1, 0.2]],
        )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.parent_id, parent_id)
        self.assertEqual(record.parent_text, parent_text)

        payload = record.payload()
        self.assertEqual(payload["parent_id"], parent_id)
        self.assertEqual(payload["parent_text"], parent_text)

    def test_retriever_returns_parent_text_and_deduplicates_by_parent_id(self):
        doc_id = str(uuid4())
        version_id = str(uuid4())
        parent_id = str(uuid4())
        parent_text = "Toàn bộ đoạn văn bản cha giàu ngữ cảnh cho LLM."

        # Hai child chunks khác nhau cùng thuộc 1 parent_id
        hit1 = VectorSearchResult(
            point_id=str(uuid4()),
            document_id=doc_id,
            version_id=version_id,
            chunk_index=0,
            file_name="guide.pdf",
            chunk_text="Đoạn con 1",
            score=0.95,
            parent_id=parent_id,
            parent_text=parent_text,
        )
        hit2 = VectorSearchResult(
            point_id=str(uuid4()),
            document_id=doc_id,
            version_id=version_id,
            chunk_index=1,
            file_name="guide.pdf",
            chunk_text="Đoạn con 2",
            score=0.85,
            parent_id=parent_id,
            parent_text=parent_text,
        )

        fake_vector_index = MagicMock()
        fake_vector_index.query.return_value = [hit1, hit2]

        retriever = QdrantActiveVersionRetriever(
            vector_index=fake_vector_index,
            embeddings=FakeEmbeddings(),
            active_version_ids=(version_id,),
            top_k=5,
        )

        # Khi parent_child_enabled = True -> Chỉ 1 Document chứa parent_text được trả về (deduplicated)
        with patch.object(settings, "parent_child_enabled", True):
            docs = retriever.invoke("câu hỏi tìm kiếm")
            self.assertEqual(len(docs), 1)
            self.assertEqual(docs[0].page_content, parent_text)
            self.assertEqual(docs[0].metadata["parent_id"], parent_id)

        # Khi parent_child_enabled = False -> 2 Documents trả về với chunk_text con riêng biệt
        with patch.object(settings, "parent_child_enabled", False):
            docs = retriever.invoke("câu hỏi tìm kiếm")
            self.assertEqual(len(docs), 2)
            self.assertEqual(docs[0].page_content, "Đoạn con 1")
            self.assertEqual(docs[1].page_content, "Đoạn con 2")
