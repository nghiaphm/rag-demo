"""Offline tests for context-aware HR UI context validation, budgeting, and orchestration."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from langchain_core.documents import Document
from langchain_core.messages import AIMessage
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.api.schemas.chat_documents import ChatRequest  # noqa: E402
from app.chat.context_budget import ContextBudgetBuilder, ContextBudgetConfig  # noqa: E402
from app.chat.orchestrator import ChatOrchestrator  # noqa: E402
from app.chat.pipeline import prepare_rag_request_from_components  # noqa: E402
from app.chat.ui_context import (  # noqa: E402
    UiPageContext,
    UiRelatedPage,
    build_selector_ui_note,
    compose_ui_aware_system_instruction,
    fit_ui_system_instruction,
)
from app.rag.prompt import SYSTEM_INSTRUCTION  # noqa: E402


class _FakeRetriever:
    def invoke(self, _query: str) -> list[Document]:
        return [
            Document(
                page_content="Chính sách nghỉ phép năm gồm 12 ngày phép cơ bản.",
                metadata={
                    "file_name": "chinh-sach-nghi-phep.pdf",
                    "document_id": "11111111-1111-4111-8111-111111111111",
                    "version_id": "22222222-2222-4222-8222-222222222222",
                    "chunk_id": "33333333-3333-4333-8333-333333333333",
                    "page": 0,
                },
            )
        ]


class _PassThroughReranker:
    def rerank(self, _query: str, documents: list[Document], **_kwargs) -> list[Document]:
        return list(documents)


class _PassThroughRewriter:
    async def rewrite(self, query: str, _turns: tuple):
        return type(
            "_Rewrite",
            (),
            {
                "retrieval_query": query,
                "metrics": type("_Metrics", (), {"mode": "unchanged", "provider_calls": 0})(),
            },
        )()


class _PassThroughExpander:
    async def expand(self, query: str) -> list[str]:
        return [query]


def _sample_ui_context() -> UiPageContext:
    return UiPageContext(
        portal="hr",
        route="/hr/documents",
        page_title="Tài liệu nhân sự",
        page_purpose="Tìm kiếm, phân nhóm, xem trước và tải tài liệu HR lên kho RAG.",
        available_features=(
            "Lọc theo nhóm Chính sách, Quy định, Quy trình",
            "Xem trước TXT, MD, XLSX và tải tài liệu mới",
        ),
        related_pages=(
            UiRelatedPage(route="/hr", title="Tổng quan nhân sự", description="Dashboard KPI và Live KB"),
            UiRelatedPage(route="/hr/guide", title="Hướng dẫn sử dụng", description="Hướng dẫn nhanh và câu hỏi mẫu"),
        ),
        selected_document_name="chinh-sach-nghi-phep.pdf",
        selected_category="POLICY",
    )


class UiContextTests(unittest.TestCase):
    def test_chat_request_validates_optional_ui_context_and_blocks_unsafe_routes(self) -> None:
        base = ChatRequest(question="Chính sách nghỉ phép?")
        self.assertIsNone(base.ui_context)

        valid = ChatRequest(
            question="Hướng dẫn thao tác trang này",
            ui_context={
                "portal": "hr",
                "route": "/hr/documents",
                "page_title": "Tài liệu nhân sự",
                "page_purpose": "Quản lý tài liệu HR.",
                "available_features": ["Tìm kiếm tài liệu", "Tải tài liệu lên"],
                "related_pages": [
                    {"route": "/hr", "title": "Tổng quan nhân sự"},
                ],
            },
        )
        self.assertIsNotNone(valid.ui_context)
        self.assertEqual(valid.ui_context.route, "/hr/documents")

        for bad_route in ("https://evil.example/hr", "../admin", "/hr/documents with space", "hr"):
            with self.assertRaises(ValidationError):
                ChatRequest(
                    question="Test",
                    ui_context={
                        "route": bad_route,
                        "page_title": "Test",
                        "page_purpose": "Test",
                    },
                )

    def test_ui_context_prompt_composition_and_tight_budget_fallback(self) -> None:
        ui = _sample_ui_context()
        composed = compose_ui_aware_system_instruction(SYSTEM_INSTRUCTION, ui)
        self.assertIn("/hr/documents", composed)
        self.assertIn("Tài liệu nhân sự", composed)
        self.assertIn("chinh-sach-nghi-phep.pdf", composed)
        self.assertIn("### 1. Giới thiệu trang hiện tại", composed)
        self.assertIn("### 5. Nguồn tài liệu tham khảo", composed)
        self.assertIn("không ép sang mẫu 5 mục", composed)

        # Strict system budget safely falls back to base_instruction without raising.
        tight = fit_ui_system_instruction(
            SYSTEM_INSTRUCTION,
            ui,
            count_tokens=lambda text: len(text),
            max_tokens=len(SYSTEM_INSTRUCTION) + 10,
        )
        self.assertEqual(tight, SYSTEM_INSTRUCTION)
        self.assertIn("/hr/documents", build_selector_ui_note(ui))

    def test_prepare_rag_request_preserves_clean_query_while_injecting_ui_context(self) -> None:
        budget_builder = ContextBudgetBuilder(
            ContextBudgetConfig(
                context_window_tokens=8192,
                system_max_tokens=1024,
                history_max_tokens=2048,
                chunks_max_tokens=3584,
                query_max_tokens=512,
                output_reserve_tokens=1024,
            )
        )
        ui = _sample_ui_context()
        prepared_with_ui = asyncio.run(
            prepare_rag_request_from_components(
                "Hướng dẫn thao tác chức năng Nhân sự hiện tại",
                history_turns=(),
                active_version_ids=("22222222-2222-4222-8222-222222222222",),
                retriever=_FakeRetriever(),
                query_rewriter=_PassThroughRewriter(),
                budget_builder=budget_builder,
                reranker=_PassThroughReranker(),
                multi_query_expander=_PassThroughExpander(),
                ui_context=ui,
            )
        )
        self.assertEqual(prepared_with_ui.original_query, "Hướng dẫn thao tác chức năng Nhân sự hiện tại")
        self.assertEqual(prepared_with_ui.retrieval_query, "Hướng dẫn thao tác chức năng Nhân sự hiện tại")
        messages_with_ui = prepared_with_ui.prompt_value.to_messages()
        self.assertIn("/hr/documents", messages_with_ui[0].content)
        self.assertIn("Hướng dẫn thao tác chức năng Nhân sự hiện tại", messages_with_ui[-1].content)
        self.assertNotIn("Ngữ cảnh trang hiện tại", messages_with_ui[-1].content)

        prepared_plain = asyncio.run(
            prepare_rag_request_from_components(
                "Chính sách nghỉ phép năm?",
                history_turns=(),
                active_version_ids=("22222222-2222-4222-8222-222222222222",),
                retriever=_FakeRetriever(),
                query_rewriter=_PassThroughRewriter(),
                budget_builder=budget_builder,
                reranker=_PassThroughReranker(),
                multi_query_expander=_PassThroughExpander(),
                ui_context=None,
            )
        )
        self.assertEqual(prepared_plain.prompt_value.to_messages()[0].content, SYSTEM_INSTRUCTION)

    def test_orchestrator_forwards_ui_context_without_breaking_plain_calls(self) -> None:
        captured: dict[str, object] = {}

        async def fake_rag_prepare(question: str, **kwargs):
            captured["question"] = question
            captured["ui_context"] = kwargs.get("ui_context")
            return type(
                "_Prepared",
                (),
                {
                    "prompt_value": MagicMock(to_messages=lambda: []),
                    "sources": [],
                    "rewrite": None,
                },
            )()

        fake_llm = MagicMock()
        bound = MagicMock()

        async def fake_ainvoke(*_args, **_kwargs):
            return AIMessage(content="no tools needed")

        bound.ainvoke = fake_ainvoke
        fake_llm.bind_tools.return_value = bound

        orchestrator = ChatOrchestrator(
            llm=fake_llm,
            tools_enabled=True,
            agentic_mode=False,
            rag_prepare=fake_rag_prepare,
        )
        ui = _sample_ui_context()
        asyncio.run(orchestrator.prepare_plan("Hướng dẫn dùng trang này", ui_context=ui))
        self.assertEqual(captured["question"], "Hướng dẫn dùng trang này")
        self.assertEqual(captured["ui_context"], ui)

        # Agentic branch injects UI context into initial system prompt
        agent_orchestrator = ChatOrchestrator(
            llm=fake_llm,
            tools_enabled=True,
            agentic_mode=True,
        )
        plan = asyncio.run(agent_orchestrator.prepare_plan("Trang này có gì?", ui_context=ui))
        self.assertEqual(plan.route, "AGENTIC")
        self.assertIn("/hr/documents", plan.agent_messages[0].content)


if __name__ == "__main__":
    unittest.main()
