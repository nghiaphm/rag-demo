"""P5-04 shared history-aware retrieval/context integration tests."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from langchain_core.documents import Document
from langchain_core.messages import AIMessage

from app.conversations.models import (
    MessageRecord,
    MessageRole,
    MessageStatus,
    SessionScope,
    SessionScopeMode,
)
from app.shared.config import settings
from app.documents.models import DocumentStatus
from app.conversations.history import HistoryTurn
from app.chat.query_rewriting import (
    QueryRewriteResult,
    RewriteMetrics,
    RewriteStatus,
)
from app.chat.pipeline import answer_question_async, prepare_rag_request


class FakeRetriever:
    def __init__(self, documents):
        self.documents = documents
        self.queries = []

    def invoke(self, query):
        self.queries.append(query)
        return self.documents


class FakeRewriter:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def rewrite(self, query, history_turns):
        self.calls.append((query, history_turns))
        return self.result


class RagIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session_id = str(uuid4())
        self.document_id = str(uuid4())
        self.deleted_document_id = str(uuid4())
        self.version_id = str(uuid4())
        self.chunk_id = str(uuid4())
        request_id = str(uuid4())
        self.turn = HistoryTurn(
            user=MessageRecord(
                session_id=self.session_id,
                sequence=1,
                role=MessageRole.USER,
                content="RAG kết hợp retrieval và generation.",
                status=MessageStatus.COMPLETED,
                request_id=request_id,
            ),
            assistant=MessageRecord(
                session_id=self.session_id,
                sequence=2,
                role=MessageRole.ASSISTANT,
                content="Nó dùng nguồn được truy xuất để tạo câu trả lời.",
                status=MessageStatus.COMPLETED,
                request_id=request_id,
            ),
        )

    async def test_selected_scope_rewrite_and_prompt_keep_separate_queries(self):
        original = "Còn nó dùng nguồn đó thế nào?"
        rewritten = "RAG dùng nguồn được truy xuất thế nào?"
        scope = SessionScope(
            mode=SessionScopeMode.SELECTED_DOCUMENTS,
            document_ids=[self.document_id, self.deleted_document_id],
        )
        loaded = SimpleNamespace(turns=(self.turn,), scope=scope)
        document_repository = SimpleNamespace()

        def get_document(document_id):
            if document_id == self.document_id:
                return SimpleNamespace(
                    status=DocumentStatus.INDEXED,
                    active_version_id=self.version_id,
                    deleted_at=None,
                )
            return SimpleNamespace(
                status=DocumentStatus.DELETED,
                active_version_id=str(uuid4()),
                deleted_at=object(),
            )

        document_repository.get_document = get_document
        rewrite_result = QueryRewriteResult(
            original_query=original,
            retrieval_query=rewritten,
            rewritten=True,
            status=RewriteStatus.REWRITTEN,
            dependency_reason="context_reference",
            metrics=RewriteMetrics(1, 2.5, 10, 4, 14, "provider"),
        )
        rewriter = FakeRewriter(rewrite_result)
        retriever = FakeRetriever(
            [
                Document(
                    page_content="Grounded chunk",
                    metadata={
                        "file_name": "guide.md",
                        "document_id": self.document_id,
                        "version_id": self.version_id,
                        "chunk_id": self.chunk_id,
                        "chunk_index": 3,
                        "page": 2,
                    },
                )
            ]
        )
        captured_versions = []

        def retriever_factory(**kwargs):
            captured_versions.append(kwargs["active_version_ids"])
            return retriever

        with patch(
            "app.chat.pipeline.MongoDocumentRepository",
            return_value=document_repository,
        ), patch(
            "app.chat.pipeline.MongoConversationRepository", return_value=object()
        ), patch(
            "app.chat.pipeline.ConversationHistoryLoader"
        ) as loader_type, patch(
            "app.chat.pipeline.create_query_rewriter", return_value=rewriter
        ), patch(
            "app.chat.pipeline.get_retriever", side_effect=retriever_factory
        ):
            loader_type.return_value.load.return_value = loaded
            prepared = await prepare_rag_request(
                original,
                database=object(),
                qdrant_client=object(),
                session_id=self.session_id,
            )

        self.assertEqual(captured_versions, [(self.version_id,)])
        self.assertEqual(retriever.queries, [rewritten])
        self.assertEqual(rewriter.calls[0][0], original)
        self.assertEqual(rewriter.calls[0][1], (self.turn,))
        self.assertEqual(prepared.original_query, original)
        self.assertEqual(prepared.retrieval_query, rewritten)
        self.assertEqual(prepared.active_version_ids, (self.version_id,))
        self.assertEqual(prepared.sources[0]["chunk_id"], self.chunk_id)
        self.assertEqual(prepared.sources[0]["version_id"], self.version_id)
        prompt_text = "\n".join(str(message.content) for message in prepared.prompt_value.to_messages())
        self.assertIn(original, prompt_text)
        self.assertNotIn(f"Câu hỏi gốc: {rewritten}", prompt_text)
        self.assertIn(self.turn.user.content, prompt_text)
        self.assertIn("[1] (guide.md, page 2)", prompt_text)
        self.assertLessEqual(
            prepared.budget.usage.total,
            settings.rag_context_window_tokens,
        )

    async def test_non_stream_generation_consumes_shared_prepared_prompt(self):
        prepared = SimpleNamespace(
            prompt_value=object(),
            sources=[{"chunk_id": self.chunk_id}],
        )

        class Llm:
            inputs = []

            async def ainvoke(self, prompt):
                self.inputs.append(prompt)
                return AIMessage(
                    content="Grounded answer [1]",
                    usage_metadata={
                        "input_tokens": 8,
                        "output_tokens": 4,
                        "total_tokens": 12,
                    },
                )

        llm = Llm()
        with patch(
            "app.chat.pipeline.prepare_rag_request", return_value=prepared
        ) as builder, patch("app.chat.pipeline.get_llm", return_value=llm):
            result = await answer_question_async(
                "Original question",
                database=object(),
                qdrant_client=object(),
                session_id=self.session_id,
            )

        builder.assert_awaited_once_with(
            "Original question",
            database=unittest.mock.ANY,
            qdrant_client=unittest.mock.ANY,
            session_id=self.session_id,
        )
        self.assertEqual(llm.inputs, [prepared.prompt_value])
        self.assertEqual(result["answer"], "Grounded answer [1]")
        self.assertEqual(result["sources"], prepared.sources)
        self.assertEqual(result["usage"]["total_tokens"], 12)


if __name__ == "__main__":
    unittest.main()
