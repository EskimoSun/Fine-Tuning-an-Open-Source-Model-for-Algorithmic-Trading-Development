"""Protect baseline provenance and missing-data rules in the Excel export."""
import unittest
from pathlib import Path

from qc_eval.export_excel import build_report

SNAPSHOT = Path(__file__).resolve().parents[1] / "src/eval_results/2026-10-19"


class ExcelReportTests(unittest.TestCase):
    def test_original_baseline_does_not_receive_repaired_judge_scores(self):
        report = build_report(SNAPSHOT)
        self.assertEqual(len(report["prompts"]), 100)
        self.assertEqual(len(report["baseline"]), 10)
        self.assertTrue(all(row["fidelity"] is None for row in report["baseline"]))
        self.assertEqual([row[5] for row in report["feedback"]], [5, 4, 3])

    def test_incompatible_dates_and_failed_execution_do_not_get_similarity_scores(self):
        report = build_report(SNAPSHOT)
        rsi, roc, future = report["behavior"]
        self.assertEqual(rsi[1:5], [16, 22, 8, 11])
        self.assertEqual(rsi[5:9], [None] * 4)
        self.assertAlmostEqual(roc[7], 0.016649746091891904)
        self.assertEqual(future[1:9], [None] * 8)

    def test_all_dimensions_and_analyst_review_survive_export(self):
        report = build_report(SNAPSHOT)
        self.assertEqual(len(report["details"]), 24)
        self.assertEqual([row[7] for row in report["feedback"]], ["Y", "Y", "Y"])
        self.assertIn("Analyst review", report["reasons"][1][3])


if __name__ == "__main__":
    unittest.main()
