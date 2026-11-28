"""Unit tests for Phase 3 Agent/SQL Trajectory Evaluator and Benchmark Matrix."""

from __future__ import annotations

import unittest


class TestAgentEvaluationAndBenchmarkMatrix(unittest.TestCase):
    def test_agent_trajectory_metrics_and_sql_guard_validation(self) -> None:
        from evaluation.scoring.agent_eval import (
            AgentEvalCase,
            AgentTurnObservation,
            evaluate_agent_trajectory,
        )

        cases = [
            AgentEvalCase(
                case_id="sql-hr-total",
                question="Tổng quỹ lương cơ bản của toàn bộ nhân sự là bao nhiêu triệu?",
                expected_route="AGENTIC",
                expected_tools=("run_sql",),
                expected_facts=("234",),
                expect_sql=True,
            ),
            AgentEvalCase(
                case_id="doc-count",
                question="Hiện có bao nhiêu tài liệu trong kho?",
                expected_route="AGENTIC",
                expected_tools=("count_documents",),
                expected_facts=("4",),
                expect_sql=False,
            ),
        ]
        observations = [
            AgentTurnObservation(
                case_id="sql-hr-total",
                actual_route="AGENTIC",
                called_tools=("run_sql",),
                generated_sql=("SELECT SUM(base_salary_million) AS total_salary FROM nhansu",),
                allowed_views=("nhansu",),
                answer="Tổng quỹ lương cơ bản là 234 triệu đồng [1].",
                citations_valid=True,
                agent_steps=2,
                latency_ms=85.0,
                ttft_ms=30.0,
                prompt_tokens=150,
                completion_tokens=25,
            ),
            AgentTurnObservation(
                case_id="doc-count",
                actual_route="AGENTIC",
                called_tools=("count_documents",),
                generated_sql=(),
                allowed_views=(),
                answer="Hiện có 4 tài liệu đang hoạt động.",
                citations_valid=True,
                agent_steps=2,
                latency_ms=45.0,
                ttft_ms=15.0,
                prompt_tokens=90,
                completion_tokens=15,
            ),
        ]

        report = evaluate_agent_trajectory(
            cases,
            observations,
            run_mode="offline_smoke",
        )
        self.assertEqual(report.run_mode, "offline_smoke")
        self.assertFalse(report.valid_for_model_quality)
        self.assertIn("OFFLINE_PLUMBING_CHECK", report.banner)
        self.assertEqual(report.route_accuracy, 1.0)
        self.assertEqual(report.tool_selection_precision, 1.0)
        self.assertEqual(report.tool_selection_recall, 1.0)
        self.assertEqual(report.sql_guard_pass_rate, 1.0)
        self.assertEqual(report.sql_execution_accuracy, 1.0)
        self.assertEqual(report.citation_validity_rate, 1.0)
        self.assertEqual(report.avg_agent_steps, 2.0)
        self.assertEqual(report.total_tokens, 280)

    def test_live_eval_guard_blocks_production_qdrant_collection(self) -> None:
        from evaluation.runner.eval_agent_cli import validate_live_eval_collection

        for forbidden in ("rag_documents", "RAG_DOCUMENTS", "", "   "):
            with self.subTest(collection=forbidden), self.assertRaises(ValueError):
                validate_live_eval_collection(forbidden)

        self.assertEqual(
            validate_live_eval_collection("rag_documents_eval"),
            "rag_documents_eval",
        )

    def test_offline_agent_smoke_runner_executes_real_duckdb_without_network(self) -> None:
        from evaluation.runner.eval_agent_cli import run_offline_agent_smoke

        report = run_offline_agent_smoke()
        self.assertEqual(report["run_mode"], "offline_smoke")
        self.assertFalse(report["valid_for_model_quality"])
        self.assertIn("OFFLINE_PLUMBING_CHECK", report["banner"])
        self.assertEqual(report["summary"]["sql_guard_pass_rate"], 1.0)
        self.assertEqual(report["summary"]["sql_execution_accuracy"], 1.0)

    def test_benchmark_matrix_configs_exclude_semantic_cache_and_pass_offline_check(self) -> None:
        from evaluation.runner.benchmark_matrix import (
            BENCHMARK_CONFIGS,
            estimate_live_provider_calls,
            run_offline_matrix_check,
        )

        self.assertEqual(set(BENCHMARK_CONFIGS.keys()), {"A", "B", "C"})
        for cfg in BENCHMARK_CONFIGS.values():
            self.assertFalse(cfg.flags.get("semantic_cache_enabled", False))

        self.assertFalse(BENCHMARK_CONFIGS["A"].flags["corrective_rag_enabled"])
        self.assertTrue(BENCHMARK_CONFIGS["B"].flags["corrective_rag_enabled"])
        self.assertTrue(BENCHMARK_CONFIGS["C"].flags["agentic_mode_enabled"])
        self.assertTrue(BENCHMARK_CONFIGS["C"].flags["excel_sql_enabled"])

        check_result = run_offline_matrix_check()
        self.assertEqual(check_result["status"], "PASS")
        self.assertFalse(check_result["valid_for_model_quality"])
        self.assertEqual(set(check_result["horizontal_dataset_configs"]), {"A", "B", "C"})
        self.assertEqual(check_result["specialized_sql_configs"], ["C"])

        estimate = estimate_live_provider_calls(include_llm_judge=True)
        self.assertGreater(estimate["estimated_groq_calls"], 0)
        self.assertGreater(estimate["estimated_gemini_embedding_calls"], 0)


if __name__ == "__main__":
    unittest.main()
