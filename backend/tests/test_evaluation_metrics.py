"""Regression tests for deterministic evaluation metrics."""

import unittest

from evaluation.metrics import answer_fact_coverage, fact_present


class EvaluationMetricTests(unittest.TestCase):
    def test_fact_matching_normalizes_unicode_dash_variants(self):
        self.assertTrue(fact_present("re-index", "Cần re‑index toàn bộ dữ liệu."))
        self.assertEqual(
            answer_fact_coverage("Cần re–index dữ liệu.", ["re-index"]),
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
