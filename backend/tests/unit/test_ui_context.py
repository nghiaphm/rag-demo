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
    UiDashboardContractStatus,
    UiDashboardDepartment,
    UiDashboardKnowledgeBase,
    UiDashboardKpi,
    UiDashboardSnapshot,
    UiPageContext,
    UiRelatedPage,
    build_selector_ui_note,
    compose_ui_aware_system_instruction,
    fit_ui_system_instruction,
    format_dashboard_snapshot_context,
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

    def test_dashboard_snapshot_validation_deterministic_stats_budget_and_pipeline_injection(self) -> None:
        # 1. Schema validation: valid snapshot accepted, negative counts rejected
        valid_req = ChatRequest(
            question="Hãy phân tích và thống kê nhân sự",
            ui_context={
                "portal": "hr",
                "route": "/hr",
                "page_title": "Tổng quan nhân sự",
                "page_purpose": "Dashboard HR",
                "dashboard_snapshot": {
                    "as_of_label": "Dữ liệu mô phỏng HR · Quý 4/2026",
                    "total_employees": 184,
                    "kpis": [
                        {
                            "label": "Tổng nhân sự",
                            "value": "184",
                            "delta_label": "+6.4% so với quý trước",
                            "trend": "up",
                        }
                    ],
                    "departments": [
                        {"department": "Kỹ thuật & Sản phẩm", "count": 68, "open_roles": 5},
                        {"department": "Vận hành & CSKH", "count": 38, "open_roles": 2},
                        {"department": "Kinh doanh", "count": 32, "open_roles": 3},
                        {"department": "Nhân sự & Hành chính", "count": 16, "open_roles": 1},
                        {"department": "Tài chính & Kế toán", "count": 16, "open_roles": 0},
                        {"department": "Marketing & Tăng trưởng", "count": 14, "open_roles": 2},
                    ],
                    "contract_statuses": [
                        {"label": "HĐ không xác định thời hạn", "count": 132},
                        {"label": "HĐ xác định thời hạn", "count": 31},
                        {"label": "Đang thử việc", "count": 14},
                        {"label": "Thực tập / Cộng tác viên", "count": 7},
                    ],
                    "knowledge_base": {
                        "total_documents": 10,
                        "indexed_documents": 8,
                        "processing_documents": 1,
                        "failed_documents": 1,
                        "total_chunks": 120,
                    },
                },
            },
        )
        self.assertIsNotNone(valid_req.ui_context)
        assert valid_req.ui_context is not None
        self.assertIsNotNone(valid_req.ui_context.dashboard_snapshot)

        with self.assertRaises(ValidationError):
            ChatRequest(
                question="Phân tích nhân sự",
                ui_context={
                    "portal": "hr",
                    "route": "/hr",
                    "page_title": "Tổng quan nhân sự",
                    "page_purpose": "Dashboard HR",
                    "dashboard_snapshot": {
                        "as_of_label": "Q4/2026",
                        "total_employees": -5,
                    },
                },
            )

        # 2. Deterministic server-side statistics formatting
        ui_with_dashboard = UiPageContext(
            portal="hr",
            route="/hr",
            page_title="Tổng quan nhân sự",
            page_purpose="Dashboard KPI nhân sự và Kho tri thức RAG.",
            available_features=(
                "Theo dõi 4 chỉ số KPI nhân sự.",
                "Phân tích biểu đồ cơ cấu 6 phòng ban và 4 nhóm hợp đồng.",
            ),
            related_pages=(
                UiRelatedPage(route="/hr/documents", title="Tài liệu nhân sự", description="Quản lý tài liệu HR"),
            ),
            dashboard_snapshot=UiDashboardSnapshot(
                as_of_label="Dữ liệu mô phỏng HR · Quý 4/2026",
                total_employees=184,
                kpis=(
                    UiDashboardKpi(
                        label="Tổng nhân sự",
                        value="184",
                        delta_label="+6.4% so với quý trước",
                        trend="up",
                    ),
                    UiDashboardKpi(
                        label="Tỉ lệ nghỉ việc",
                        value="2.1%",
                        delta_label="-0.4% so với cùng kỳ",
                        trend="down",
                    ),
                ),
                departments=(
                    UiDashboardDepartment(department="Kỹ thuật & Sản phẩm", count=68, open_roles=5),
                    UiDashboardDepartment(department="Vận hành & CSKH", count=38, open_roles=2),
                    UiDashboardDepartment(department="Kinh doanh", count=32, open_roles=3),
                    UiDashboardDepartment(department="Nhân sự & Hành chính", count=16, open_roles=1),
                    UiDashboardDepartment(department="Tài chính & Kế toán", count=16, open_roles=0),
                    UiDashboardDepartment(department="Marketing & Tăng trưởng", count=14, open_roles=2),
                ),
                contract_statuses=(
                    UiDashboardContractStatus(label="HĐ không xác định thời hạn", count=132),
                    UiDashboardContractStatus(label="HĐ xác định thời hạn", count=31),
                    UiDashboardContractStatus(label="Đang thử việc", count=14),
                    UiDashboardContractStatus(label="Thực tập / Cộng tác viên", count=7),
                ),
                knowledge_base=UiDashboardKnowledgeBase(
                    total_documents=10,
                    indexed_documents=8,
                    processing_documents=1,
                    failed_documents=1,
                    total_chunks=120,
                ),
            ),
        )

        snapshot_block = format_dashboard_snapshot_context(ui_with_dashboard)
        self.assertIn("Dữ liệu thống kê Dashboard HR hiện tại", snapshot_block)
        self.assertIn("tổng=184, tổng vị trí đang tuyển=13", snapshot_block)
        self.assertIn("Kỹ thuật & Sản phẩm: 68 nhân sự (37.0%)", snapshot_block)
        self.assertIn("Marketing & Tăng trưởng: 14 nhân sự (7.6%)", snapshot_block)
        self.assertIn("HĐ không xác định thời hạn: 132 nhân sự (71.7%)", snapshot_block)
        self.assertIn("sẵn sàng (INDEXED)=8 (80.0%)", snapshot_block)

        # 3. Fits strictly inside default RAG_SYSTEM_MAX_TOKENS (1024)
        budget_builder = ContextBudgetBuilder(
            ContextBudgetConfig(
                context_window_tokens=8192,
                system_max_tokens=1024,
                history_max_tokens=2048,
                chunks_max_tokens=3584,
                query_max_tokens=512,
                output_reserve_tokens=1024,
                chars_per_token=3.0,
            )
        )
        fitted_system = fit_ui_system_instruction(
            SYSTEM_INSTRUCTION,
            ui_with_dashboard,
            budget_builder.counter.system,
            1024,
        )
        self.assertLessEqual(budget_builder.counter.system(fitted_system), 1024)
        self.assertIn("### 1. Tóm tắt điều hành", fitted_system)
        self.assertIn("### 3. Bảng phân bổ cơ cấu nhân sự", fitted_system)

        # Selector note directs HR Dashboard analytics away from document inventory tools
        selector_note = build_selector_ui_note(ui_with_dashboard)
        self.assertIn("HR Dashboard", selector_note)

        # 4. Pipeline injects dashboard block into Context even when Qdrant returns 0 chunks
        class _EmptyRetriever:
            def invoke(self, _query: str) -> list[Document]:
                return []

        prepared_empty_kb = asyncio.run(
            prepare_rag_request_from_components(
                "Hãy phân tích và thống kê nhân sự",
                history_turns=(),
                active_version_ids=(),
                retriever=_EmptyRetriever(),
                query_rewriter=_PassThroughRewriter(),
                budget_builder=budget_builder,
                reranker=_PassThroughReranker(),
                multi_query_expander=_PassThroughExpander(),
                ui_context=ui_with_dashboard,
            )
        )
        self.assertEqual(prepared_empty_kb.original_query, "Hãy phân tích và thống kê nhân sự")
        self.assertEqual(prepared_empty_kb.retrieval_query, "Hãy phân tích và thống kê nhân sự")
        human_content = prepared_empty_kb.prompt_value.to_messages()[-1].content
        self.assertIn("Kỹ thuật & Sản phẩm: 68 nhân sự (37.0%)", human_content)
        self.assertNotIn("(không có tài liệu liên quan)", human_content)

        # And preserves [1] citation ordinal when RAG chunks ARE present
        prepared_with_chunks = asyncio.run(
            prepare_rag_request_from_components(
                "Hãy tiến hành phân tích trang Nhân sự",
                history_turns=(),
                active_version_ids=("22222222-2222-4222-8222-222222222222",),
                retriever=_FakeRetriever(),
                query_rewriter=_PassThroughRewriter(),
                budget_builder=budget_builder,
                reranker=_PassThroughReranker(),
                multi_query_expander=_PassThroughExpander(),
                ui_context=ui_with_dashboard,
            )
        )
        human_with_chunks = prepared_with_chunks.prompt_value.to_messages()[-1].content
        self.assertIn("Kỹ thuật & Sản phẩm: 68 nhân sự (37.0%)", human_with_chunks)
        self.assertIn("[1] (chinh-sach-nghi-phep.pdf", human_with_chunks)

        # 5. Agentic orchestrator injects dashboard snapshot while keeping original_question clean
        fake_llm = MagicMock()
        agent_orchestrator = ChatOrchestrator(
            llm=fake_llm,
            tools_enabled=True,
            agentic_mode=True,
        )
        plan = asyncio.run(
            agent_orchestrator.prepare_plan(
                "Hãy phân tích và thống kê nhân sự",
                ui_context=ui_with_dashboard,
            )
        )
        self.assertEqual(plan.original_question, "Hãy phân tích và thống kê nhân sự")
        self.assertIn("Kỹ thuật & Sản phẩm: 68 nhân sự (37.0%)", plan.agent_messages[-1].content)


if __name__ == "__main__":
    unittest.main()
