"""Unit tests for Phase 1 RAGAS metrics and baseline evaluation helpers."""

from __future__ import annotations

import unittest

from evaluation.scoring.ragas_metrics import (
    RagasSample,
    aggregate_ragas_scores,
    compute_latency_percentiles,
    evaluate_ragas_sample,
)


class TestRagasMetrics(unittest.TestCase):
    def test_evaluate_ragas_sample_deterministic_high_quality(self) -> None:
        sample = RagasSample(
            question="Vector của gemini-embedding-001 có bao nhiêu chiều?",
            answer="Vector của gemini-embedding-001 có 3072 chiều.",
            contexts=("Model gemini-embedding-001 tạo vector 3072 chiều.",),
            expected_facts=("3072",),
            expected_sources=("llm-embedding.md",),
            retrieved_sources=("llm-embedding.md",),
            latency_ms=42.0,
            ttft_ms=12.0,
        )
        score = evaluate_ragas_sample(sample)
        self.assertEqual(score.context_precision, 1.0)
        self.assertEqual(score.context_recall, 1.0)
        self.assertEqual(score.faithfulness, 1.0)
        self.assertGreater(score.answer_relevancy, 0.8)
        self.assertGreater(score.overall_score, 0.9)

    def test_evaluate_ragas_sample_uses_llm_judge_hook_when_provided(self) -> None:
        sample = RagasSample(
            question="Q?",
            answer="A.",
            contexts=("ctx",),
        )
        score = evaluate_ragas_sample(
            sample,
            llm_judge=lambda _s: {
                "context_precision": 0.9,
                "context_recall": 0.8,
                "faithfulness": 1.0,
                "answer_relevancy": 0.7,
            },
        )
        self.assertEqual(score.context_precision, 0.9)
        self.assertEqual(score.context_recall, 0.8)
        self.assertEqual(score.faithfulness, 1.0)
        self.assertEqual(score.answer_relevancy, 0.7)
        self.assertEqual(score.overall_score, 0.85)

    def test_aggregate_and_latency_percentiles(self) -> None:
        s1 = evaluate_ragas_sample(
            RagasSample(
                question="What is Qdrant?",
                answer="Qdrant is a vector database.",
                contexts=("Qdrant is a vector database for embeddings.",),
                expected_facts=("vector database",),
            )
        )
        s2 = evaluate_ragas_sample(
            RagasSample(
                question="Unknown topic?",
                answer="No info.",
                contexts=(),
                expected_facts=("missing",),
            )
        )
        agg = aggregate_ragas_scores([s1, s2])
        self.assertGreater(agg["overall_score"], 0.0)
        self.assertLess(agg["overall_score"], 1.0)

        lat = compute_latency_percentiles([10.0, 20.0, 30.0, 40.0, 100.0], [5.0, 10.0, 15.0])
        self.assertEqual(lat["p50_ms"], 30.0)
        self.assertEqual(lat["p95_ms"], 88.0)
        self.assertEqual(lat["ttft_p50_ms"], 10.0)

    def test_golden_datasets_v2_and_agent_sql_have_verifiable_ground_truth(self) -> None:
        import io
        import json
        from pathlib import Path
        import duckdb
        import pyarrow.parquet as pq
        from app.documents.excel.tabular import extract_workbook_tables

        repo_root = Path(__file__).resolve().parents[3]
        eval_dir = repo_root / "backend" / "evaluation" / "datasets"
        corpus_dir = eval_dir / "corpus"

        v2_path = eval_dir / "golden_set_v2.json"
        sql_path = eval_dir / "agent_sql_golden_set.json"
        self.assertTrue(v2_path.is_file(), "golden_set_v2.json must exist")
        self.assertTrue(sql_path.is_file(), "agent_sql_golden_set.json must exist")

        v2 = json.loads(v2_path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(v2["cases"]), 12)
        in_scope = [c for c in v2["cases"] if not c["expect_refusal"]]
        out_scope = [c for c in v2["cases"] if c["expect_refusal"]]
        self.assertGreaterEqual(len(in_scope), 9)
        self.assertGreaterEqual(len(out_scope), 3)

        for case in v2["cases"]:
            self.assertTrue(str(case.get("ground_truth", "")).strip(), f"Missing ground_truth in {case['id']}")
            for src in case.get("expected_sources", []):
                self.assertTrue((corpus_dir / src).is_file(), f"Missing corpus file: {src}")

        sql_ds = json.loads(sql_path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(sql_ds["cases"]), 8)

        parquet_tables: dict[tuple[str, str], object] = {}
        for case in sql_ds["cases"]:
            self.assertTrue(str(case.get("ground_truth", "")).strip(), f"Missing ground_truth in {case['id']}")
            self.assertTrue(case.get("expected_tools"), f"Missing expected_tools in {case['id']}")
            if case.get("verification_sql"):
                wb_rel = case["workbook_path"]
                wb_file = repo_root / wb_rel
                self.assertTrue(wb_file.is_file(), f"Missing workbook: {wb_rel}")
                tbl_name = case["table_name"]
                cache_key = (wb_rel, tbl_name)
                if cache_key not in parquet_tables:
                    extracted = extract_workbook_tables(wb_file.read_bytes())
                    matched = next(t for t in extracted if t.table_name == tbl_name)
                    parquet_tables[cache_key] = pq.read_table(io.BytesIO(matched.parquet_bytes))

                conn = duckdb.connect(":memory:")
                try:
                    conn.register(tbl_name, parquet_tables[cache_key])
                    scalar_val = conn.execute(case["verification_sql"]).fetchone()[0]
                finally:
                    conn.close()

                expected_num = case["expected_numeric_result"]
                if isinstance(expected_num, float):
                    self.assertAlmostEqual(float(scalar_val), expected_num, places=2)
                else:
                    self.assertEqual(int(scalar_val), int(expected_num))

    def test_dataset_evaluation_separates_correct_refusal_rate_from_faithfulness(self) -> None:
        from evaluation.scoring.ragas_metrics import evaluate_dataset_samples

        samples = [
            # In-scope sample: faithful (1.0)
            RagasSample(
                question="Collection mặc định tên gì?",
                answer="Collection mặc định tên rag_documents.",
                contexts=("Collection ứng dụng mặc định có tên rag_documents.",),
                expected_facts=("rag_documents",),
                expected_sources=("qdrant.md",),
                retrieved_sources=("qdrant.md",),
                ground_truth="Collection mặc định là rag_documents.",
                expect_refusal=False,
            ),
            # Out-of-scope sample 1: correct refusal (empty context -> old code gave faithfulness=0.0!)
            RagasSample(
                question="Giá vàng hôm nay là bao nhiêu?",
                answer="Không tìm thấy thông tin về giá vàng trong tài liệu đã tải lên.",
                contexts=(),
                expect_refusal=True,
                ground_truth="Từ chối trả lời do ngoài phạm vi tài liệu.",
            ),
            # Out-of-scope sample 2: hallucinated instead of refusing -> incorrect refusal
            RagasSample(
                question="Thủ đô Nhật Bản là gì?",
                answer="Thủ đô Nhật Bản là Tokyo với 14 triệu dân.",
                contexts=(),
                expect_refusal=True,
                ground_truth="Từ chối trả lời do ngoài phạm vi tài liệu.",
            ),
        ]

        report = evaluate_dataset_samples(samples, scoring_method="deterministic_heuristic")
        self.assertEqual(report.scoring_method, "deterministic_heuristic")
        self.assertEqual(report.in_scope_count, 1)
        self.assertEqual(report.out_of_scope_count, 2)
        # Faithfulness MUST be 1.0 (computed strictly over the 1 in-scope sample, not dragged down by refusals!)
        self.assertEqual(report.in_scope_summary["faithfulness"], 1.0)
        # Correct refusal rate MUST be 0.5 (1 out of 2 out-of-scope samples refused properly)
        self.assertEqual(report.correct_refusal_count, 1)
        self.assertEqual(report.correct_refusal_rate, 0.5)

    def test_custom_llm_judge_never_mixes_heuristic_scores_when_judge_fails(self) -> None:
        from types import SimpleNamespace
        from evaluation.scoring.llm_judge import CustomLlmJudge
        from evaluation.scoring.ragas_metrics import evaluate_dataset_samples

        call_idx = 0

        def _fake_llm_invoke(_prompt: str):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return SimpleNamespace(
                    content='{"context_precision": 0.9, "context_recall": 0.8, "faithfulness": 1.0, "answer_relevancy": 0.9}'
                )
            raise TimeoutError("simulated provider timeout on sample 2")

        judge = CustomLlmJudge(invoke_fn=_fake_llm_invoke, max_retries=0)
        samples = [
            RagasSample(
                question="Q1?",
                answer="Chunk size is 500.",
                contexts=("Chunk size is 500.",),
                expected_facts=("500",),
                expect_refusal=False,
            ),
            RagasSample(
                question="Q2?",
                answer="Overlap is 50.",
                contexts=("Overlap is 50.",),
                expected_facts=("50",),
                expect_refusal=False,
            ),
        ]

        report = evaluate_dataset_samples(
            samples,
            scoring_method="custom_llm_judge",
            custom_judge=judge,
        )
        self.assertEqual(report.scoring_method, "custom_llm_judge")
        self.assertEqual(report.judge_error_count, 1)
        self.assertEqual(report.valid_in_scope_count, 1)
        # Sample 2 failed in LLM judge -> score MUST be None, NEVER backfilled with heuristic 1.0!
        self.assertIsNotNone(report.sample_results[0]["scores"])
        self.assertIsNone(report.sample_results[1]["scores"])
        # Mean context_precision MUST remain purely 0.9 (from sample 1), not (0.9 + 1.0)/2 = 0.95!
        self.assertEqual(report.in_scope_summary["context_precision"], 0.9)
        self.assertEqual(report.in_scope_summary["context_recall"], 0.8)


if __name__ == "__main__":
    unittest.main()
