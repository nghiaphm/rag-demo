"""Offline unit tests for Phase 3 Agentic Orchestration (multi-step tools + rag_search)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from langchain_core.documents import Document
from langchain_core.messages import AIMessage

from app.chat.orchestrator import ChatOrchestrator
from app.tool_use.contracts import ToolContractError, validate_arguments


def _doc(content: str, *, file_name: str, chunk_index: int = 0) -> Document:
    return Document(
        page_content=content,
        metadata={
            "chunk_id": str(uuid4()),
            "document_id": str(uuid4()),
            "version_id": str(uuid4()),
            "file_name": file_name,
            "chunk_index": chunk_index,
        },
    )


class _ScriptedAgentModel:
    """Offline fake LangChain chat model supporting bind_tools and scripted multi-step responses."""

    def __init__(self, responses: list[AIMessage]) -> None:
        self._responses = list(responses)
        self.bound_calls: list[tuple[list[dict], str]] = []
        self.invocations: list[list[object]] = []

    async def ainvoke(self, messages, **_kwargs):
        self.invocations.append(list(messages))
        if not self._responses:
            raise AssertionError("No scripted response left")
        return self._responses.pop(0)

    def bind_tools(self, tools: list[dict], *, tool_choice: str = "auto"):
        self.bound_calls.append((tools, tool_choice))
        parent = self

        class _Bound:
            async def ainvoke(self, messages, **_kwargs):
                parent.invocations.append(list(messages))
                if not parent._responses:
                    raise AssertionError("No scripted response left")
                return parent._responses.pop(0)

        return _Bound()


def _fake_queries():
    queries = MagicMock()
    queries.count_documents.return_value = {"count": 2, "include_deleted": False}
    queries.list_documents.return_value = {
        "items": [{"file_name": "q3-report.pdf", "status": "ACTIVE"}],
        "offset": 0,
        "limit": 10,
        "has_more": False,
    }
    return queries


class TestAgenticOrchestrator(unittest.IsolatedAsyncioTestCase):
    async def test_agentic_multi_step_combines_list_documents_and_iterative_rag_search(self) -> None:
        doc_rev = _doc("Q3 revenue reached $12M.", file_name="q3-report.pdf", chunk_index=0)
        doc_exp = _doc("Q3 operating expenses were $8M.", file_name="q3-report.pdf", chunk_index=1)

        def _rag_search(query: str, top_k: int) -> list[Document]:
            if "revenue" in query.lower():
                return [doc_rev][:top_k]
            if "expenses" in query.lower():
                return [doc_exp][:top_k]
            return []

        model = _ScriptedAgentModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"id": "c1", "name": "list_documents", "args": {"limit": 5}}],
                    usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                ),
                AIMessage(
                    content="",
                    tool_calls=[{"id": "c2", "name": "rag_search", "args": {"query": "Q3 revenue", "top_k": 3}}],
                    usage_metadata={"input_tokens": 20, "output_tokens": 6, "total_tokens": 26},
                ),
                AIMessage(
                    content="",
                    tool_calls=[{"id": "c3", "name": "rag_search", "args": {"query": "Q3 expenses", "top_k": 3}}],
                    usage_metadata={"input_tokens": 25, "output_tokens": 6, "total_tokens": 31},
                ),
                AIMessage(
                    content="Báo cáo Q3 ghi nhận doanh thu $12M và chi phí $8M.",
                    usage_metadata={"input_tokens": 30, "output_tokens": 12, "total_tokens": 42},
                ),
            ]
        )

        orchestrator = ChatOrchestrator(
            llm=model,
            queries=_fake_queries(),
            tools_enabled=True,
            agentic_mode=True,
            max_agent_steps=4,
            rag_search_fn=_rag_search,
        )
        plan = await orchestrator.prepare_plan("Tìm các file báo cáo Q3 và tóm tắt doanh thu, chi phí")
        self.assertEqual(plan.route, "AGENTIC")

        result = await orchestrator.generate_json(plan)
        self.assertIn("$12M", result["answer"])
        self.assertIn("$8M", result["answer"])
        self.assertEqual(len(result["sources"]), 2)
        self.assertEqual(
            result["usage"],
            {"input_tokens": 85, "output_tokens": 29, "total_tokens": 114},
        )
        # Verify tool schemas exposed all 4 agentic tools
        tool_names = {t["function"]["name"] for t in model.bound_calls[0][0]}
        self.assertEqual(tool_names, {"count_documents", "list_documents", "rag_search", "query_excel_table"})

    async def test_agentic_max_steps_guard_forces_bounded_final_synthesis(self) -> None:
        model = _ScriptedAgentModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"id": "c1", "name": "count_documents", "args": {}}],
                    usage_metadata={"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
                ),
                AIMessage(
                    content="",
                    tool_calls=[{"id": "c2", "name": "count_documents", "args": {}}],
                    usage_metadata={"input_tokens": 12, "output_tokens": 4, "total_tokens": 16},
                ),
                # Step 3 is the forced final synthesis with tool_choice="none"
                AIMessage(
                    content="Tổng cộng có 2 tài liệu.",
                    usage_metadata={"input_tokens": 15, "output_tokens": 8, "total_tokens": 23},
                ),
            ]
        )

        orchestrator = ChatOrchestrator(
            llm=model,
            queries=_fake_queries(),
            tools_enabled=True,
            agentic_mode=True,
            max_agent_steps=2,
        )
        plan = await orchestrator.prepare_plan("Count documents")
        result = await orchestrator.generate_json(plan)
        self.assertEqual(result["answer"], "Tổng cộng có 2 tài liệu.")
        self.assertEqual(model.bound_calls[-1], ([], "none"))

    async def test_legacy_mode_preserved_when_agentic_mode_disabled(self) -> None:
        model = _ScriptedAgentModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"id": "c1", "name": "count_documents", "args": {}}],
                    usage_metadata={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
                ),
                AIMessage(
                    content="Có 2 tài liệu.",
                    usage_metadata={"input_tokens": 8, "output_tokens": 4, "total_tokens": 12},
                ),
            ]
        )
        orchestrator = ChatOrchestrator(
            llm=model,
            queries=_fake_queries(),
            tools_enabled=True,
            agentic_mode=False,
        )
        plan = await orchestrator.prepare_plan("How many documents?")
        self.assertEqual(plan.route, "DOCUMENT_TOOLS")
        result = await orchestrator.generate_json(plan)
        self.assertEqual(result["answer"], "Có 2 tài liệu.")
        tool_names = {t["function"]["name"] for t in model.bound_calls[0][0]}
        self.assertEqual(tool_names, {"count_documents", "list_documents"})

    def test_rag_search_contract_validation(self) -> None:
        valid = validate_arguments("rag_search", {"query": "Qdrant vector", "top_k": 3})
        self.assertEqual(valid, {"query": "Qdrant vector", "top_k": 3})
        with self.assertRaises(ToolContractError):
            validate_arguments("rag_search", {"query": "", "top_k": 3})
        with self.assertRaises(ToolContractError):
            validate_arguments("rag_search", {"query": "ok", "top_k": 99})


if __name__ == "__main__":
    unittest.main()
