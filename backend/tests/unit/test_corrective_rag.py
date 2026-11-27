"""Offline unit tests for Phase 2 Self-corrective Retrieval (Corrective RAG)."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from uuid import uuid4

from langchain_core.documents import Document

from app.api.streaming.event_adapter import status_frame
from app.api.streaming.sse_schema import (
    SSEDeltaData,
    SSEDeltaEvent,
    SSEDoneData,
    SSEDoneEvent,
    SSEMetadataData,
    SSEMetadataEvent,
    SSEStartData,
    SSEStartEvent,
    SSEStatusData,
    SSEStatusEvent,
    SSETranscript,
)
from app.chat.corrective import (
    CorrectiveRagRunner,
    EvidenceEvaluator,
    QueryCorrector,
    RelevanceGrade,
    RetrievalGrader,
)
from app.chat.pipeline import prepare_rag_request_from_components
from app.rag.reranker import PassThroughReranker


def _doc(content: str, *, file_name: str = "doc.md", idx: int = 0) -> Document:
    return Document(
        page_content=content,
        metadata={
            "chunk_id": str(uuid4()),
            "document_id": str(uuid4()),
            "version_id": str(uuid4()),
            "file_name": file_name,
            "chunk_index": idx,
        },
    )


class _FakeWebSearch:
    def __init__(self, docs: list[Document]) -> None:
        self.docs = docs
        self.queries: list[str] = []

    async def search(self, query: str, *, max_results: int = 3) -> list[Document]:
        self.queries.append(query)
        return self.docs[:max_results]


class _FakeRetriever:
    def __init__(self, mapping: dict[str, list[Document]]) -> None:
        self.mapping = mapping
        self.calls: list[str] = []

    def invoke(self, query: str) -> list[Document]:
        self.calls.append(query)
        for key, docs in self.mapping.items():
            if key in query.lower():
                return docs
        return []


class TestCorrectiveRag(unittest.IsolatedAsyncioTestCase):
    async def test_grader_passes_relevant_and_flags_irrelevant(self) -> None:
        grader = RetrievalGrader()
        relevant = await grader.grade(
            "Qdrant vector database collection",
            [_doc("Qdrant is a vector database using collection rag_documents.")],
        )
        self.assertEqual(relevant.grade, RelevanceGrade.RELEVANT)

        irrelevant = await grader.grade(
            "What is the capital of Japan?",
            [_doc("Chunk size is 500 characters with 50 overlap.")],
        )
        self.assertEqual(irrelevant.grade, RelevanceGrade.IRRELEVANT)

        empty = await grader.grade("Any question?", [])
        self.assertEqual(empty.grade, RelevanceGrade.IRRELEVANT)

    async def test_grader_falls_back_to_heuristic_on_llm_timeout(self) -> None:
        class _SlowLLM:
            async def ainvoke(self, _messages):
                await asyncio.sleep(0.2)
                return SimpleNamespace(content='{"grade":"IRRELEVANT"}')

        grader = RetrievalGrader(llm=_SlowLLM(), timeout_seconds=0.01)
        res = await grader.grade(
            "Qdrant vector collection",
            [_doc("Qdrant vector collection stores embeddings.")],
        )
        self.assertEqual(res.grade, RelevanceGrade.RELEVANT)

    async def test_runner_skips_retry_when_initial_docs_are_relevant(self) -> None:
        runner = CorrectiveRagRunner(max_retries=2)
        retry_calls = 0

        async def _retry(_q: str) -> list[Document]:
            nonlocal retry_calls
            retry_calls += 1
            return []

        outcome = await runner.run(
            question="How does Qdrant vector database work?",
            initial_query="Qdrant vector database",
            initial_documents=[_doc("Qdrant vector database stores embeddings.")],
            retrieve_and_rerank=_retry,
        )
        self.assertEqual(outcome.grade, RelevanceGrade.RELEVANT)
        self.assertEqual(outcome.retries_used, 0)
        self.assertFalse(outcome.strict_fallback_triggered)
        self.assertEqual(retry_calls, 0)

    async def test_runner_retries_on_irrelevant_and_recovers(self) -> None:
        runner = CorrectiveRagRunner(max_retries=1)
        statuses: list[tuple[str, str]] = []

        async def _on_status(step: str, msg: str) -> None:
            statuses.append((step, msg))

        async def _retry(_q: str) -> list[Document]:
            return [_doc("Gemini embedding model produces 3072 dimensions.")]

        outcome = await runner.run(
            question="Gemini embedding dimensions?",
            initial_query="embedding model",
            initial_documents=[_doc("Unrelated text about cooking recipes.")],
            retrieve_and_rerank=_retry,
            on_status=_on_status,
        )
        self.assertEqual(outcome.grade, RelevanceGrade.RELEVANT)
        self.assertEqual(outcome.retries_used, 1)
        self.assertEqual(len(outcome.tried_queries), 2)
        self.assertFalse(outcome.strict_fallback_triggered)
        self.assertTrue(any(step == "query_correction" for step, _ in statuses))

    async def test_runner_triggers_strict_fallback_when_retries_exhausted(self) -> None:
        runner = CorrectiveRagRunner(max_retries=1)

        async def _retry(_q: str) -> list[Document]:
            return [_doc("Still unrelated content about weather.")]

        outcome = await runner.run(
            question="Price of gold today?",
            initial_query="gold price",
            initial_documents=[_doc("Unrelated chunking config.")],
            retrieve_and_rerank=_retry,
        )
        self.assertEqual(outcome.grade, RelevanceGrade.IRRELEVANT)
        self.assertEqual(outcome.retries_used, 1)
        self.assertTrue(outcome.strict_fallback_triggered)
        self.assertFalse(outcome.used_web_fallback)
        self.assertEqual(outcome.documents, [])

    async def test_runner_uses_web_search_fallback_when_configured(self) -> None:
        web = _FakeWebSearch([_doc("Gold price today is $2600/oz.", file_name="web")])
        runner = CorrectiveRagRunner(max_retries=1, web_search_provider=web)

        async def _retry(_q: str) -> list[Document]:
            return []

        outcome = await runner.run(
            question="Price of gold today?",
            initial_query="gold price",
            initial_documents=[],
            retrieve_and_rerank=_retry,
        )
        self.assertTrue(outcome.used_web_fallback)
        self.assertFalse(outcome.strict_fallback_triggered)
        self.assertEqual(len(outcome.documents), 1)
        self.assertEqual(len(web.queries), 1)

    async def test_runner_respects_expired_deadline(self) -> None:
        runner = CorrectiveRagRunner(max_retries=2)
        retry_calls = 0

        async def _retry(_q: str) -> list[Document]:
            nonlocal retry_calls
            retry_calls += 1
            return []

        outcome = await runner.run(
            question="Anything?",
            initial_query="anything",
            initial_documents=[],
            retrieve_and_rerank=_retry,
            deadline=0.0,  # already expired
        )
        self.assertEqual(retry_calls, 0)
        self.assertEqual(outcome.retries_used, 0)
        self.assertTrue(outcome.strict_fallback_triggered)

    async def test_query_corrector_never_repeats_tried_query(self) -> None:
        corrector = QueryCorrector()
        res = await corrector.correct("Qdrant vector collection", ["qdrant vector collection"])
        self.assertNotEqual(res.corrected_query.lower(), "qdrant vector collection")
        self.assertTrue(bool(res.corrected_query.strip()))

    async def test_evidence_evaluator_detects_grounded_vs_ungrounded(self) -> None:
        evaluator = EvidenceEvaluator()
        docs = [_doc("Chunk size is 500 characters and overlap is 50.")]
        ok = await evaluator.evaluate("What is chunk size?", "Chunk size is 500 characters.", docs)
        self.assertTrue(ok.grounded)
        bad = await evaluator.evaluate(
            "What is chunk size?",
            "Tokyo is the capital of Japan and has 14 million residents.",
            docs,
        )
        self.assertFalse(bad.grounded)

    async def test_pipeline_integration_with_corrective_runner(self) -> None:
        class _FakeRewriter:
            async def rewrite(self, question: str, _turns):
                return SimpleNamespace(retrieval_query=question, metrics=SimpleNamespace(mode="passthrough"))

        class _FakeExpander:
            async def expand(self, query: str) -> list[str]:
                return [query]

        retriever = _FakeRetriever(
            {
                "initial": [_doc("Completely unrelated text.", file_name="noise.md")],
                "qdrant": [_doc("Qdrant stores embeddings in collections.", file_name="qdrant.md")],
            }
        )
        runner = CorrectiveRagRunner(max_retries=1)
        prepared = await prepare_rag_request_from_components(
            "qdrant collection",
            history_turns=(),
            active_version_ids=("v1",),
            retriever=retriever,
            query_rewriter=_FakeRewriter(),
            reranker=PassThroughReranker(),
            multi_query_expander=_FakeExpander(),
            corrective_runner=runner,
        )
        self.assertIsNotNone(prepared.corrective_outcome)
        self.assertEqual(prepared.corrective_outcome.grade, RelevanceGrade.RELEVANT)

    def test_sse_status_event_and_frame_are_valid(self) -> None:
        frame = status_frame(sequence=2, step="retrieval_grade", message="Grading...")
        self.assertIn("event: status\n", frame)
        transcript = SSETranscript(
            events=[
                SSEStartEvent(
                    data=SSEStartData(
                        sequence=1,
                        request_id=uuid4(),
                        session_id=None,
                        user_message_id=None,
                        assistant_message_id=None,
                        mode="STATELESS",
                    )
                ),
                SSEStatusEvent(
                    data=SSEStatusData(sequence=2, step="retrieval_grade", message="Grading...")
                ),
                SSEMetadataEvent(
                    data=SSEMetadataData(sequence=3, model="test-model", sources=[])
                ),
                SSEDeltaEvent(data=SSEDeltaData(sequence=4, content="Answer")),
                SSEDoneEvent(data=SSEDoneData(sequence=5, usage=None)),
            ]
        )
        self.assertEqual(transcript.reconstructed_answer, "Answer")

    def test_get_grader_llm_uses_configured_corrective_grader_model(self) -> None:
        from app.rag.llm import get_grader_llm
        from tests._test_env import override_settings

        with override_settings(corrective_grader_model="llama-3.1-8b-instant"):
            grader_llm = get_grader_llm()
            model_name = getattr(grader_llm, "model_name", None) or getattr(grader_llm, "model", None)
            self.assertEqual(model_name, "llama-3.1-8b-instant")

    async def test_create_corrective_runner_wires_llm_into_grader_and_corrector_without_web_search(self) -> None:
        from app.chat.corrective import create_corrective_runner

        calls: list[str] = []

        class _ScriptedGraderLLM:
            async def ainvoke(self, messages):
                prompt_text = "\n".join(str(getattr(m, "content", "")) for m in messages)
                if "Rewrite the user query" in prompt_text:
                    calls.append("corrector")
                    return SimpleNamespace(content="qdrant rag_documents collection")
                calls.append("grader")
                if "rag_documents" in prompt_text:
                    return SimpleNamespace(
                        content='{"grade":"RELEVANT","relevant_indices":[0],"reason":"exact match"}'
                    )
                return SimpleNamespace(
                    content='{"grade":"IRRELEVANT","relevant_indices":[],"reason":"off-topic"}'
                )

        runner = create_corrective_runner(llm=_ScriptedGraderLLM(), max_retries=1)
        self.assertIsNone(runner.web_search_provider)

        async def _retry(q: str) -> list[Document]:
            if "rag_documents" in q:
                return [_doc("Default collection is rag_documents.", file_name="qdrant.md")]
            return []

        outcome = await runner.run(
            question="Tên collection mặc định?",
            initial_query="collection",
            initial_documents=[_doc("Unrelated cooking recipe.")],
            retrieve_and_rerank=_retry,
        )
        self.assertEqual(outcome.grade, RelevanceGrade.RELEVANT)
        self.assertEqual(outcome.retries_used, 1)
        self.assertEqual(calls, ["grader", "corrector", "grader"])
        self.assertFalse(outcome.used_web_fallback)
        self.assertFalse(outcome.strict_fallback_triggered)


if __name__ == "__main__":
    unittest.main()
