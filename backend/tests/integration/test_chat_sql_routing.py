"""Integration tests cho T4.1 & T4.3: định tuyến `run_sql` + `rag_search`, JSON/SSE parity, ngân sách catalog và che cột nhạy cảm."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, SystemMessage
import pyarrow as pa
import pyarrow.parquet as pq

from app.api.routes.chat import _encode_provider_stream_impl
from app.api.streaming.sse_schema import SSETranscript
from app.api.streaming.stream_metrics import StreamMetricTracker
from app.chat.context_budget import ApproximateTokenCounter, ContextBudgetConfig
from app.chat.orchestrator import ChatOrchestrator
from app.documents.excel.sql_service import (
    ExcelSqlService,
    format_catalog_summary_for_prompt,
)
from app.documents.models import (
    DocumentRecord,
    DocumentStatus,
    DocumentTableCatalogRecord,
    TableColumnSchema,
    new_uuid,
)
from app.infrastructure.duckdb_executor import DuckDBSqlExecutor
from app.shared.auth import UserContext
from app.shared.config import settings


class FakeCatalogRepo:
    def __init__(
        self,
        documents: list[DocumentRecord],
        catalogs: list[DocumentTableCatalogRecord],
    ) -> None:
        self._documents = list(documents)
        self._catalogs = list(catalogs)

    def list_documents(
        self,
        *,
        include_deleted: bool = False,
        offset: int = 0,
        limit: int = 500,
    ) -> list[DocumentRecord]:
        docs = [
            d
            for d in self._documents
            if include_deleted or (d.status != DocumentStatus.DELETED and d.deleted_at is None)
        ]
        return docs[offset : offset + limit]

    def list_tables_for_versions(
        self,
        version_ids: list[str],
        *,
        tenant_id: str | None = None,
    ) -> list[DocumentTableCatalogRecord]:
        id_set = set(version_ids)
        return [
            c
            for c in self._catalogs
            if c.version_id in id_set and (tenant_id is None or c.tenant_id == tenant_id)
        ]


class ScriptedToolModel:
    """Fake LLM trả chuỗi AIMessage theo kịch bản, ghi nhận tools đã bind và messages đầu vào."""

    def __init__(self, responses: list[AIMessage]) -> None:
        self.responses = list(responses)
        self.bound_schemas: list[list[dict]] = []
        self.invocations: list[list[object]] = []

    def bind_tools(self, schemas: list[dict], tool_choice: str = "auto") -> "ScriptedToolModel":
        self.bound_schemas.append(list(schemas))
        return self

    async def ainvoke(self, messages: list[object], **kwargs: object) -> AIMessage:
        self.invocations.append(list(messages))
        if not self.responses:
            raise AssertionError("ScriptedToolModel ran out of scripted AIMessage responses")
        return self.responses.pop(0)


def _tool_call_ai_message(
    calls: list[tuple[str, str, dict]],
    *,
    input_tokens: int = 40,
    output_tokens: int = 15,
) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"id": call_id, "name": name, "args": args}
            for call_id, name, args in calls
        ],
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )


def _final_ai_message(
    text: str,
    *,
    input_tokens: int = 60,
    output_tokens: int = 25,
) -> AIMessage:
    return AIMessage(
        content=text,
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )


class ChatSqlRoutingIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.doc_id = new_uuid()
        self.ver_id = new_uuid()
        self.parquet_key = f"default/{self.doc_id}/v1/tables/nhan_su.parquet"
        table = pa.table(
            {
                "ma_nv": ["NV01", "NV02", "NV03"],
                "phong_ban": ["KyThuat", "KyThuat", "NhanSu"],
                "luong_co_ban": [2500, 3500, 2000],
            }
        )
        buf = pa.BufferOutputStream()
        pq.write_table(table, buf)
        self.parquet_bytes_map: dict[str, bytes] = {
            self.parquet_key: buf.getvalue().to_pybytes()
        }

        self.doc_record = DocumentRecord(
            document_id=self.doc_id,
            tenant_id="default",
            file_name="hr_employees_mock.xlsx",
            status=DocumentStatus.INDEXED,
            active_version_id=self.ver_id,
            owner_id="user-hr",
            allowed_roles=["hr"],
        )
        self.catalog_record = DocumentTableCatalogRecord(
            tenant_id="default",
            document_id=self.doc_id,
            version_id=self.ver_id,
            table_name="nhan_su",
            sheet_name="NhanSu",
            parquet_key=self.parquet_key,
            row_count=3,
            columns=[
                TableColumnSchema(
                    name="ma_nv",
                    original_name="Mã NV",
                    type="VARCHAR",
                    nullable=False,
                    description="Cột gốc 'Mã NV', kiểu VARCHAR, giá trị mẫu: NV01, NV02",
                ),
                TableColumnSchema(
                    name="phong_ban",
                    original_name="Phòng ban",
                    type="VARCHAR",
                    nullable=False,
                    description="Cột gốc 'Phòng ban', kiểu VARCHAR, giá trị mẫu: KyThuat, NhanSu",
                ),
                TableColumnSchema(
                    name="luong_co_ban",
                    original_name="Lương cơ bản",
                    type="INT64",
                    nullable=False,
                    description="Cột gốc 'Lương cơ bản', kiểu INT64, giá trị mẫu: 2500, 3500, 2000",
                ),
            ],
            sample_rows=[
                {"ma_nv": "NV01", "phong_ban": "KyThuat", "luong_co_ban": 2500},
                {"ma_nv": "NV02", "phong_ban": "KyThuat", "luong_co_ban": 3500},
            ],
        )

        self.executor = DuckDBSqlExecutor(
            storage_backend="s3",
            s3_bucket="unit-test-bucket",
            s3_region="ap-southeast-1",
            s3_endpoint_url="https://s3.ap-southeast-1.amazonaws.com",
            query_access_key_id="AKIA_QUERY_READONLY",
            query_secret_access_key="SECRET_QUERY_READONLY",
            ingest_access_key_id="AKIA_INGEST_WRITER",
            memory_limit="256MB",
            threads=1,
            timeout_seconds=5.0,
            max_rows=50,
            _test_parquet_bytes_by_key=self.parquet_bytes_map,
        )

        self.user = UserContext(
            user_id="user-hr",
            username="hr_user",
            roles=["hr"],
            tenant_id="default",
            is_authenticated=True,
        )
        self.repo = FakeCatalogRepo([self.doc_record], [self.catalog_record])
        self.sql_service = ExcelSqlService(repository=self.repo, executor=self.executor)

    def _make_orchestrator(
        self,
        model: ScriptedToolModel,
        *,
        sql_service: ExcelSqlService | None = None,
        rag_docs: list[Document] | None = None,
        budget_config: ContextBudgetConfig | None = None,
    ) -> ChatOrchestrator:
        docs_to_return = list(rag_docs or [])
        with (
            patch.object(settings, "storage_backend", "s3"),
            patch.object(settings, "excel_parquet_ingestion_enabled", True),
            patch.object(settings, "agentic_mode_enabled", True),
            patch.object(settings, "excel_sql_enabled", True),
        ):
            return ChatOrchestrator(
                llm=model,
                tools_enabled=True,
                agentic_mode=True,
                excel_sql_enabled=True,
                sql_service=sql_service if sql_service is not None else self.sql_service,
                current_user=self.user,
                tenant_id="default",
                budget_config=budget_config,
                rag_search_fn=lambda q, k: docs_to_return,
            )

    def test_calculation_question_uses_run_sql_and_attaches_excel_source_citation(
        self,
    ) -> None:
        model = ScriptedToolModel(
            [
                _tool_call_ai_message(
                    [
                        (
                            "call_sql_1",
                            "run_sql",
                            {
                                "sql": "SELECT SUM(luong_co_ban) AS tong_luong FROM nhan_su WHERE phong_ban = 'KyThuat'"
                            },
                        )
                    ]
                ),
                _final_ai_message("Tổng lương cơ bản của phòng KyThuat là 6000."),
            ]
        )
        orchestrator = self._make_orchestrator(model)

        async def _run():
            plan = await orchestrator.prepare_plan("Tính tổng lương cơ bản phòng KyThuat?")
            return await orchestrator.generate_json(plan)

        result = asyncio.run(_run())
        self.assertIn("6000", result["answer"])
        self.assertEqual(len(result["sources"]), 1)
        src = result["sources"][0]
        self.assertEqual(src["file_name"], "hr_employees_mock.xlsx")
        self.assertEqual(src["sheet_name"], "NhanSu")
        self.assertEqual(src["document_id"], self.doc_id)
        self.assertEqual(src["version_id"], self.ver_id)
        self.assertTrue(src["source"].startswith("sql:nhan_su"))

    def test_policy_question_uses_rag_search_without_calling_run_sql(self) -> None:
        policy_doc_id = new_uuid()
        policy_ver_id = new_uuid()
        rag_docs = [
            Document(
                page_content="Nhân viên chính thức được nghỉ phép năm 12 ngày hưởng nguyên lương.",
                metadata={
                    "chunk_id": "chunk-policy-1",
                    "document_id": policy_doc_id,
                    "version_id": policy_ver_id,
                    "file_name": "hr_policy_leave.pdf",
                    "page": 3,
                    "chunk_index": 0,
                },
            )
        ]
        model = ScriptedToolModel(
            [
                _tool_call_ai_message(
                    [("call_rag_1", "rag_search", {"query": "quy định nghỉ phép năm"})]
                ),
                _final_ai_message("Theo chính sách, nhân viên được nghỉ phép năm 12 ngày."),
            ]
        )
        orchestrator = self._make_orchestrator(model, rag_docs=rag_docs)

        async def _run():
            plan = await orchestrator.prepare_plan("Quy định số ngày nghỉ phép năm là bao nhiêu?")
            return await orchestrator.generate_json(plan)

        result = asyncio.run(_run())
        self.assertIn("12 ngày", result["answer"])
        self.assertEqual(len(result["sources"]), 1)
        self.assertEqual(result["sources"][0]["file_name"], "hr_policy_leave.pdf")
        self.assertEqual(result["sources"][0]["document_id"], policy_doc_id)

    def test_combined_question_coordinates_run_sql_and_rag_search_in_same_turn(
        self,
    ) -> None:
        rag_docs = [
            Document(
                page_content="NV02 hoàn thành xuất sắc kiến trúc dữ liệu và hỗ trợ đào tạo nội bộ.",
                metadata={
                    "chunk_id": "chunk-eval-2",
                    "document_id": self.doc_id,
                    "version_id": self.ver_id,
                    "file_name": "hr_employees_mock.xlsx",
                    "sheet_name": "NhanSu",
                    "row_index": 3,
                    "chunk_index": 1,
                },
            )
        ]
        model = ScriptedToolModel(
            [
                _tool_call_ai_message(
                    [
                        (
                            "call_sql_top",
                            "run_sql",
                            {
                                "sql": "SELECT ma_nv, luong_co_ban FROM nhan_su ORDER BY luong_co_ban DESC LIMIT 1"
                            },
                        )
                    ]
                ),
                _tool_call_ai_message(
                    [
                        (
                            "call_rag_note",
                            "rag_search",
                            {"query": "NV02 nhận xét đánh giá"},
                        )
                    ]
                ),
                _final_ai_message(
                    "Nhân viên có lương cao nhất là NV02 (3500), với đánh giá hoàn thành xuất sắc kiến trúc dữ liệu."
                ),
            ]
        )
        orchestrator = self._make_orchestrator(model, rag_docs=rag_docs)

        async def _run():
            plan = await orchestrator.prepare_plan(
                "Ai có lương cơ bản cao nhất và nhận xét đánh giá của người đó thế nào?"
            )
            return await orchestrator.generate_json(plan)

        result = asyncio.run(_run())
        self.assertIn("NV02", result["answer"])
        self.assertIn("3500", result["answer"])
        self.assertEqual(len(result["sources"]), 2)
        source_kinds = {
            "sql" if str(s.get("source", "")).startswith("sql:") else "rag"
            for s in result["sources"]
        }
        self.assertEqual(source_kinds, {"sql", "rag"})

    def test_invalid_sql_column_error_allows_agent_to_self_correct_within_max_steps(
        self,
    ) -> None:
        model = ScriptedToolModel(
            [
                _tool_call_ai_message(
                    [
                        (
                            "call_bad_sql",
                            "run_sql",
                            {"sql": "SELECT cot_khong_ton_tai FROM nhan_su"},
                        )
                    ]
                ),
                _tool_call_ai_message(
                    [
                        (
                            "call_fixed_sql",
                            "run_sql",
                            {"sql": "SELECT COUNT(*) AS so_nv FROM nhan_su"},
                        )
                    ]
                ),
                _final_ai_message("Bảng nhân sự có tổng cộng 3 nhân viên."),
            ]
        )
        orchestrator = self._make_orchestrator(model)

        async def _run():
            plan = await orchestrator.prepare_plan("Có bao nhiêu nhân viên trong bảng?")
            return await orchestrator.generate_json(plan)

        result = asyncio.run(_run())
        self.assertIn("3 nhân viên", result["answer"])
        # Kiểm tra ToolMessage ở bước 2 có chứa thông báo lỗi của bước 1 để LLM tự sửa
        second_step_messages = model.invocations[1]
        tool_msg_contents = [
            getattr(m, "content", "")
            for m in second_step_messages
            if m.__class__.__name__ == "ToolMessage"
        ]
        self.assertTrue(any("TOOL_INVALID_ARGUMENTS" in c for c in tool_msg_contents))

    def test_json_and_sse_stream_parity_for_answer_sources_and_tool_calls(self) -> None:
        def _build_scripted_model() -> ScriptedToolModel:
            return ScriptedToolModel(
                [
                    _tool_call_ai_message(
                        [
                            (
                                "call_sql_parity",
                                "run_sql",
                                {
                                    "sql": "SELECT AVG(luong_co_ban) AS luong_tb FROM nhan_su WHERE phong_ban = 'KyThuat'"
                                },
                            )
                        ]
                    ),
                    _final_ai_message("Lương cơ bản trung bình phòng KyThuat là 3000."),
                ]
            )

        json_model = _build_scripted_model()
        sse_model = _build_scripted_model()
        json_orchestrator = self._make_orchestrator(json_model)
        sse_orchestrator = self._make_orchestrator(sse_model)

        async def _run_both():
            question = "Lương trung bình phòng KyThuat là bao nhiêu?"
            json_plan = await json_orchestrator.prepare_plan(question)
            json_res = await json_orchestrator.generate_json(json_plan)

            sse_plan = await sse_orchestrator.prepare_plan(question)
            state = {"content_parts": [], "usage": None, "finalized": False}
            tracker = StreamMetricTracker()
            frames: list[str] = []
            async for frame in _encode_provider_stream_impl(
                request_id=new_uuid(),
                prepared=sse_plan,
                state=state,
                tracker=tracker,
                orchestrator=sse_orchestrator,
            ):
                frames.append(frame)
            parsed_events = []
            for raw_frame in frames:
                lines = [ln for ln in raw_frame.strip().splitlines() if ln.strip()]
                ev_name = lines[0].removeprefix("event: ").strip()
                ev_data = __import__("json").loads(lines[1].removeprefix("data: ").strip())
                parsed_events.append({"event": ev_name, "data": ev_data})
            transcript = SSETranscript.model_validate({"events": parsed_events})
            return json_res, transcript

        json_result, sse_transcript = asyncio.run(_run_both())
        event_names = [e.event for e in sse_transcript.events]
        self.assertEqual(event_names, ["start", "metadata", "delta", "done"])

        sse_metadata = next(e for e in sse_transcript.events if e.event == "metadata")
        sse_deltas = "".join(
            e.data.content for e in sse_transcript.events if e.event == "delta"
        )
        sse_sources = [
            s.model_dump(exclude_none=True) for s in sse_metadata.data.sources
        ]
        json_sources = [
            {k: v for k, v in s.items() if v is not None}
            for s in json_result["sources"]
        ]

        self.assertEqual(json_result["answer"], sse_deltas)
        self.assertEqual(json_sources, sse_sources)
        self.assertEqual(len(json_model.invocations), len(sse_model.invocations))

    def test_zero_authorized_tables_omits_run_sql_and_catalog_from_prompt(self) -> None:
        empty_repo = FakeCatalogRepo([], [])
        empty_sql_service = ExcelSqlService(repository=empty_repo, executor=self.executor)
        model = ScriptedToolModel(
            [_final_ai_message("Không có bảng Excel nào trong phạm vi phiên này.")]
        )
        orchestrator = self._make_orchestrator(model, sql_service=empty_sql_service)

        async def _run():
            plan = await orchestrator.prepare_plan("Hỏi thông tin chung")
            return plan

        plan = asyncio.run(_run())
        self.assertFalse(plan.include_run_sql)
        bound_tool_names = {
            t["function"]["name"] for t in model.bound_schemas[0]
        } if model.bound_schemas else set()
        self.assertNotIn("run_sql", bound_tool_names)
        system_msg = next(
            m for m in plan.agent_messages if isinstance(m, SystemMessage)
        )
        self.assertNotIn("Danh mục bảng Excel", str(system_msg.content))

    def test_sensitive_columns_hide_sample_values_and_large_catalog_fits_system_budget(
        self,
    ) -> None:
        # 1. Kiểm tra che giá trị mẫu của cột nhạy cảm (`luong_co_ban`, `so_cccd`, `so_tai_khoan`)
        bindings = self.sql_service.list_authorized_tables(
            user=self.user,
            tenant_id="default",
        )
        counter = ApproximateTokenCounter(chars_per_token=3.0)
        summary = format_catalog_summary_for_prompt(
            bindings,
            question="Thống kê lương phòng kỹ thuật",
            count_tokens=counter.system,
            max_tokens=1024,
        )
        # Tên cột nhạy cảm và kiểu dữ liệu vẫn hiển thị để LLM viết SQL
        self.assertIn("`luong_co_ban`", summary)
        self.assertIn("INT64", summary)
        # Nhưng giá trị mẫu nhạy cảm (2500, 3500, 2000) hoàn toàn không xuất hiện trong prompt
        self.assertNotIn("2500", summary)
        self.assertNotIn("3500", summary)
        self.assertNotIn("2000", summary)

        # 2. Kiểm tra catalog lớn (25 bảng) không vượt RAG_SYSTEM_MAX_TOKENS
        many_docs: list[DocumentRecord] = []
        many_cats: list[DocumentTableCatalogRecord] = []
        for idx in range(25):
            did = new_uuid()
            vid = new_uuid()
            many_docs.append(
                DocumentRecord(
                    document_id=did,
                    tenant_id="default",
                    file_name=f"report_{idx:02d}.xlsx",
                    status=DocumentStatus.INDEXED,
                    active_version_id=vid,
                    owner_id="user-hr",
                    allowed_roles=["hr"],
                )
            )
            many_cats.append(
                DocumentTableCatalogRecord(
                    tenant_id="default",
                    document_id=did,
                    version_id=vid,
                    table_name=f"bang_du_lieu_{idx:02d}",
                    sheet_name=f"Sheet_{idx:02d}",
                    parquet_key=f"default/{did}/v1/tables/bang_du_lieu_{idx:02d}.parquet",
                    row_count=500,
                    columns=[
                        TableColumnSchema(
                            name=f"cot_chi_tieu_{c}",
                            original_name=f"Cột chỉ tiêu số {c}",
                            type="DOUBLE",
                            nullable=True,
                            description=f"Mô tả chi tiết cho cột chỉ tiêu số {c} trong báo cáo {idx}",
                        )
                        for c in range(12)
                    ],
                    sample_rows=[
                        {f"cot_chi_tieu_{c}": c * 10.5 for c in range(12)}
                        for _ in range(3)
                    ],
                )
            )
        large_service = ExcelSqlService(
            repository=FakeCatalogRepo(many_docs, many_cats),
            executor=self.executor,
        )
        tight_budget = ContextBudgetConfig(
            context_window_tokens=8192,
            system_max_tokens=512,
            history_max_tokens=2048,
            chunks_max_tokens=3584,
            query_max_tokens=512,
            output_reserve_tokens=1024,
            chars_per_token=3.0,
        )
        model = ScriptedToolModel([_final_ai_message("Đã kiểm tra danh mục.")])
        orchestrator = self._make_orchestrator(
            model,
            sql_service=large_service,
            budget_config=tight_budget,
        )

        async def _prepare_large():
            return await orchestrator.prepare_plan(
                "Phân tích số liệu trong bang_du_lieu_17?"
            )

        plan = asyncio.run(_prepare_large())
        self.assertTrue(plan.include_run_sql)
        system_msg = next(
            m for m in plan.agent_messages if isinstance(m, SystemMessage)
        )
        self.assertLessEqual(
            counter.system(str(system_msg.content)),
            tight_budget.system_max_tokens,
        )
        self.assertIn("bang_du_lieu_17", str(system_msg.content))

    def test_chat_stream_persistent_initializes_excel_sql_service_lazily_without_502(
        self,
    ) -> None:
        from types import SimpleNamespace
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.routes.chat import router as chat_router
        from app.conversations.models import (
            MessageRecord,
            MessageRole,
            MessageStatus,
            SessionRecord,
        )
        from app.conversations.service import StreamingTurn

        session_id = new_uuid()
        session_record = SessionRecord(session_id=session_id, title="Phiên HR")

        class _Cursor(list):
            def sort(self, *_args, **_kwargs):
                return self

            def skip(self, n: int):
                return _Cursor(self[n:])

            def limit(self, n: int):
                return _Cursor(self[:n])

        class _Collection:
            def __init__(self, items: list[dict] | None = None) -> None:
                self._items = list(items or [])

            def find(self, *_args, **_kwargs):
                return _Cursor(self._items)

            def find_one(self, query: dict, *_args, **_kwargs):
                for item in self._items:
                    if item.get("_id") == query.get("_id"):
                        return item
                return None

            def count_documents(self, *_args, **_kwargs) -> int:
                return len(self._items)

        fake_db = {
            "documents": _Collection([self.doc_record.to_mongo()]),
            "document_versions": _Collection([]),
            "ingestion_jobs": _Collection([]),
            "document_table_catalogs": _Collection([self.catalog_record.to_mongo()]),
            "sessions": _Collection([session_record.to_mongo()]),
            "messages": _Collection([]),
        }

        class _FakeConversationService:
            def begin_streaming_turn(self, *, session_id, question, model, attachments=()):
                req_id = new_uuid()
                user_msg = MessageRecord(
                    session_id=session_id,
                    sequence=1,
                    role=MessageRole.USER,
                    content=question,
                    status=MessageStatus.COMPLETED,
                    request_id=req_id,
                )
                assistant_msg = MessageRecord(
                    session_id=session_id,
                    sequence=2,
                    role=MessageRole.ASSISTANT,
                    status=MessageStatus.STREAMING,
                    model=model,
                    request_id=req_id,
                )
                return StreamingTurn(
                    request_id=req_id,
                    user_message=user_msg,
                    assistant_message=assistant_msg,
                )

            def finalize_streaming_turn(self, *_args, **_kwargs) -> None:
                return None

        app = FastAPI()
        app.include_router(chat_router)
        app.state.cloud_connections = SimpleNamespace(
            mongodb=SimpleNamespace(database=fake_db),
            qdrant=SimpleNamespace(client=object()),
        )
        client = TestClient(app)
        scripted_model = ScriptedToolModel(
            [_final_ai_message("Đã khởi tạo luồng trả lời thành công.")]
        )

        with (
            patch.object(settings, "tool_use_enabled", True),
            patch.object(settings, "agentic_mode_enabled", True),
            patch.object(settings, "excel_sql_enabled", True),
            patch.object(settings, "excel_parquet_ingestion_enabled", True),
            patch.object(settings, "storage_backend", "s3"),
            patch("app.chat.orchestrator.get_llm", return_value=scripted_model),
            patch(
                "app.infrastructure.duckdb_executor.create_duckdb_sql_executor",
                return_value=self.executor,
            ),
            patch(
                "app.api.routes.chat.create_conversation_service",
                return_value=_FakeConversationService(),
            ),
        ):
            response = client.post(
                "/chat/stream",
                json={
                    "question": "Hãy phân tích và thống kê nhân sự",
                    "session_id": session_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("event: start", response.text)
        self.assertIn("event: done", response.text)

    def test_agentic_rag_search_and_run_sql_respect_selected_documents_session_scope(
        self,
    ) -> None:
        from app.conversations.history import LoadedHistory
        from app.conversations.models import SessionRecord, SessionScope, SessionScopeMode
        from app.infrastructure.storage import LocalFileStorage

        doc2_id = new_uuid()
        ver2_id = new_uuid()
        parquet2_key = f"default/{doc2_id}/v1/tables/luong_bi_mat.parquet"
        table2 = pa.table({"ma_nv": ["NV99"], "luong_co_ban": [99999]})
        buf2 = io.BytesIO() if "io" in globals() else __import__("io").BytesIO()
        pq.write_table(table2, buf2)

        doc2_record = DocumentRecord(
            document_id=doc2_id,
            file_name="luong_bi_mat.xlsx",
            status=DocumentStatus.INDEXED,
            active_version_id=ver2_id,
            tenant_id="default",
        )
        cat2_record = DocumentTableCatalogRecord(
            tenant_id="default",
            document_id=doc2_id,
            version_id=ver2_id,
            table_name="luong_bi_mat",
            sheet_name="BiMat",
            parquet_key=parquet2_key,
            row_count=1,
            columns=[TableColumnSchema(name="ma_nv", original_name="ma_nv", type="VARCHAR")],
        )

        # Fake Mongo database supporting MongoDocumentRepository(database) for active_version_ids
        class _DocCollection:
            def __init__(self, docs: list[dict]) -> None:
                self._docs = docs

            def find_one(self, query: dict, *_args, **_kwargs):
                for item in self._docs:
                    if item.get("_id") == query.get("_id"):
                        return item
                return None

            def find(self, *_args, **_kwargs):
                return list(self._docs)

        fake_database = {
            "documents": _DocCollection([self.doc_record.to_mongo(), doc2_record.to_mongo()]),
            "document_versions": _DocCollection([]),
            "ingestion_jobs": _DocCollection([]),
        }

        scoped_session = SessionRecord(
            session_id=new_uuid(),
            title="Scoped Session",
            scope=SessionScope(
                mode=SessionScopeMode.SELECTED_DOCUMENTS,
                document_ids=[self.doc_id],
            ),
        )

        class _ScopedHistoryLoader:
            def load(self, session_id: str) -> LoadedHistory:
                return LoadedHistory(session=scoped_session, turns=())

        observed_version_ids: list[tuple[str, ...]] = []

        class _FakeRetriever:
            def invoke(self, query: str) -> list[Document]:
                return [
                    Document(
                        page_content=f"Chính sách nhân sự áp dụng cho {query}",
                        metadata={
                            "chunk_id": new_uuid(),
                            "document_id": self_outer.doc_id,
                            "version_id": self_outer.ver_id,
                            "file_name": "nhan_su.xlsx",
                            "chunk_index": 0,
                        },
                    )
                ]

        self_outer = self

        def _fake_get_retriever(*, qdrant_client=None, active_version_ids=None, **_kwargs):
            observed_version_ids.append(tuple(active_version_ids or ()))
            if not active_version_ids:
                class _EmptyRetriever:
                    def invoke(self, _q: str) -> list[Document]:
                        return []
                return _EmptyRetriever()
            return _FakeRetriever()

        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = LocalFileStorage(Path(tmp_dir))
            storage.put(self.parquet_key, self.parquet_bytes_map[self.parquet_key])
            storage.put(parquet2_key, buf2.getvalue())

            local_executor = DuckDBSqlExecutor(
                storage_backend="local",
                s3_bucket=None,
                query_access_key_id=None,
                query_secret_access_key=None,
                local_parquet_loader=storage.get,
            )
            multi_repo = FakeCatalogRepo(
                [self.doc_record, doc2_record],
                [self.catalog_record, cat2_record],
            )
            sql_service = ExcelSqlService(repository=multi_repo, executor=local_executor)

            model = ScriptedToolModel(
                [
                    _tool_call_ai_message(
                        [
                            ("call_sql", "run_sql", {"sql": "SELECT COUNT(*) AS c FROM nhan_su"}),
                            ("call_rag", "rag_search", {"query": "chính sách nhân sự", "top_k": 2}),
                        ]
                    ),
                    _final_ai_message("Có 3 nhân viên và chính sách nhân sự hợp lệ [1]."),
                ]
            )

            from tests._test_env import override_settings

            with (
                override_settings(
                    storage_backend="local",
                    excel_parquet_ingestion_enabled=True,
                ),
                patch("app.chat.agent_tools.get_retriever", side_effect=_fake_get_retriever),
            ):
                orchestrator = ChatOrchestrator(
                    llm=model,
                    history_loader=_ScopedHistoryLoader(),
                    tools_enabled=True,
                    agentic_mode=True,
                    excel_sql_enabled=True,
                    sql_service=sql_service,
                )
                plan = asyncio.run(
                    orchestrator.prepare_plan(
                        "Thống kê số nhân viên và tóm tắt chính sách",
                        database=fake_database,
                        qdrant_client=object(),
                        session_id=scoped_session.session_id,
                    )
                )
                # Prompt catalog must ONLY expose nhan_su (doc1), NOT luong_bi_mat (doc2)
                sys_prompt = str(plan.agent_messages[0].content)
                self.assertIn("nhan_su", sys_prompt)
                self.assertNotIn("luong_bi_mat", sys_prompt)
                self.assertEqual(plan.active_version_ids, (self.ver_id,))

                result = asyncio.run(orchestrator.generate_json(plan))

            self.assertEqual(observed_version_ids, [(self.ver_id,)])
            self.assertIn("3 nhân viên", result["answer"])
            self.assertEqual(len(result["sources"]), 2)


if __name__ == "__main__":
    unittest.main()
