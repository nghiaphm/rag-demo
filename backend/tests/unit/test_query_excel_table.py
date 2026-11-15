"""Offline unit tests for structured Excel querying (`query_excel_table`)."""

from __future__ import annotations

import io
import unittest
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage
from openpyxl import Workbook

from app.chat.orchestrator import ChatOrchestrator
from app.documents.excel.query import query_workbook_bytes
from app.tool_use.contracts import ToolContractError, validate_arguments


def _sample_xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Budget"
    ws.append(["Department", "Quarter", "Revenue", "Headcount"])
    ws.append(["Engineering", "Q3", "$1,200.50", 12])
    ws.append(["Engineering", "Q4", 1500, 14])
    ws.append(["Sales", "Q3", 800, 8])
    ws.append(["Sales", "Q4", 950, 9])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class _ScriptedExcelAgentModel:
    def __init__(self, responses: list[AIMessage]) -> None:
        self._responses = list(responses)

    def bind_tools(self, _tools: list[dict], *, tool_choice: str = "auto"):
        parent = self

        class _Bound:
            async def ainvoke(self, _messages, **_kwargs):
                return parent._responses.pop(0)

        return _Bound()


class TestQueryExcelTable(unittest.IsolatedAsyncioTestCase):
    def test_query_workbook_bytes_rows_filter_and_aggregations(self) -> None:
        xlsx = _sample_xlsx_bytes()

        rows_res = query_workbook_bytes(
            xlsx,
            filter_column="Department",
            filter_value="engineering",
            operation="rows",
        )
        self.assertEqual(rows_res["matched_count"], 2)
        self.assertEqual(len(rows_res["rows"]), 2)
        self.assertEqual(rows_res["rows"][0]["Quarter"], "Q3")

        count_res = query_workbook_bytes(
            xlsx,
            filter_column="Quarter",
            filter_value="Q3",
            operation="count",
        )
        self.assertEqual(count_res["matched_count"], 2)

        sum_res = query_workbook_bytes(
            xlsx,
            filter_column="Department",
            filter_value="Engineering",
            aggregate_column="Revenue",
            operation="sum",
        )
        self.assertEqual(sum_res["numeric_count"], 2)
        self.assertEqual(sum_res["value"], 2700.5)

        avg_res = query_workbook_bytes(
            xlsx,
            aggregate_column="Headcount",
            operation="avg",
        )
        self.assertEqual(avg_res["value"], 10.75)

        min_res = query_workbook_bytes(xlsx, aggregate_column="Headcount", operation="min")
        max_res = query_workbook_bytes(xlsx, aggregate_column="Headcount", operation="max")
        self.assertEqual(min_res["value"], 8.0)
        self.assertEqual(max_res["value"], 14.0)

    def test_validate_arguments_for_query_excel_table(self) -> None:
        valid = validate_arguments(
            "query_excel_table",
            {
                "file_name": "budget.xlsx",
                "filter_column": "Department",
                "filter_value": "Sales",
                "aggregate_column": "Revenue",
                "operation": "sum",
            },
        )
        self.assertEqual(valid["operation"], "sum")
        with self.assertRaises(ToolContractError):
            validate_arguments("query_excel_table", {"operation": "drop_table"})

    async def test_agentic_orchestrator_executes_query_excel_table(self) -> None:
        xlsx = _sample_xlsx_bytes()
        model = _ScriptedExcelAgentModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "x1",
                            "name": "query_excel_table",
                            "args": {
                                "file_name": "budget.xlsx",
                                "filter_column": "Department",
                                "filter_value": "Engineering",
                                "aggregate_column": "Revenue",
                                "operation": "sum",
                            },
                        }
                    ],
                    usage_metadata={"input_tokens": 12, "output_tokens": 6, "total_tokens": 18},
                ),
                AIMessage(
                    content="Tổng doanh thu của Engineering là 2700.5.",
                    usage_metadata={"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
                ),
            ]
        )
        orchestrator = ChatOrchestrator(
            llm=model,
            queries=MagicMock(),
            tools_enabled=True,
            agentic_mode=True,
            excel_loader_fn=lambda name: (name or "budget.xlsx", xlsx),
        )
        plan = await orchestrator.prepare_plan("Tính tổng Revenue của phòng Engineering trong budget.xlsx")
        result = await orchestrator.generate_json(plan)
        self.assertIn("2700.5", result["answer"])
        self.assertEqual(result["usage"], {"input_tokens": 32, "output_tokens": 16, "total_tokens": 48})


if __name__ == "__main__":
    unittest.main()
