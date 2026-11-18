"""Feedback-loop contracts: bounds, secrets, provenance, successful termination."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qc_eval.auto_repair import digest, feedback_request, repair_one
from qc_eval.config import load_env

SPEC = {"id": "test", "prompt": "Trade SPY", "template_id": "test"}
ORIGINAL = "class Original(QCAlgorithm):\n    pass\n"
FIXED = "class Fixed(QCAlgorithm):\n    pass\n"


class ConfigTests(unittest.TestCase):
    def test_env_is_data_not_shell_and_existing_environment_wins(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"TEST_QC_VALUE": "existing"}):
            path = Path(tmp) / ".env"
            path.write_text('export TEST_QC_VALUE="private value"\nTEST_QC_LITERAL=\'$(never-run)\' # comment\n')
            try:
                load_env(path)
                self.assertEqual(os.environ["TEST_QC_VALUE"], "existing")
                self.assertEqual(os.environ["TEST_QC_LITERAL"], "$(never-run)")
            finally:
                os.environ.pop("TEST_QC_LITERAL", None)


class FeedbackTests(unittest.TestCase):
    def source(self, root):
        path = root / "qwen_base/test.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"output": ORIGINAL, "model_id": "actual-qwen"}))
        return path

    def test_only_safe_error_fields_are_sent_and_credentials_redacted(self):
        with patch.dict(os.environ, {"QC_API_TOKEN": "private-qc-token-value"}):
            request = feedback_request(SPEC, ORIGINAL, {"status": "runtime_error",
                "error": "bad method private-qc-token-value", "headers": "hidden-header",
                "raw_backtest": "hidden-account-info", "logs": ["real QC error"]})
        self.assertNotIn("private-qc-token-value", request)
        self.assertNotIn("hidden-header", request)
        self.assertNotIn("hidden-account-info", request)
        self.assertIn("real QC error", request)

    def test_repairs_from_actual_error_preserves_original_and_stops_on_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.source(root)
            before = source.read_bytes()
            failed = {"status": "runtime_error", "error": "QC missing API"}
            completed = {"status": "completed", "backtest_id": "real-shaped-id"}
            with patch("qc_eval.auto_repair.RUNS", root), patch("qc_eval.auto_repair.generate", return_value=(FIXED, "actual-qwen")) as generate, patch(
                    "qc_eval.auto_repair.ensure_evaluation", side_effect=[failed, completed]):
                state = repair_one("qwen_base", SPEC, object(), max_repairs=3)
            self.assertEqual(state["repairs_used"], 1)
            self.assertEqual(source.read_bytes(), before)
            self.assertIn("QC missing API", generate.call_args[0][1])
            result = json.loads((root / "qwen_base_qc_repaired/test.json").read_text())
            self.assertEqual(result["intervention"], "model_qc_feedback_repair")
            self.assertEqual(result["repair"]["source_sha256"], digest(ORIGINAL))
            self.assertEqual(result["qc_evaluation"]["status"], "completed")

    def test_failed_attempt_budget_and_infrastructure_do_not_produce_success(self):
        for status, expected_calls in (("runtime_error", 2), ("infrastructure_error", 0)):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.source(root)
                with patch("qc_eval.auto_repair.RUNS", root), patch("qc_eval.auto_repair.generate", return_value=(FIXED, "actual-qwen")) as generate, patch(
                        "qc_eval.auto_repair.ensure_evaluation", return_value={"status": status}):
                    state = repair_one("qwen_base", SPEC, object(), max_repairs=2)
                self.assertEqual(generate.call_count, expected_calls)
                self.assertEqual(state["status"], status)
                self.assertFalse((root / "qwen_base_qc_repaired/test.json").exists())

    def test_resume_uses_saved_model_reply_without_another_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.source(root)
            with patch("qc_eval.auto_repair.RUNS", root), patch("qc_eval.auto_repair.generate", return_value=(FIXED, "actual-qwen")), patch(
                    "qc_eval.auto_repair.ensure_evaluation", side_effect=[{"status": "runtime_error"}, KeyboardInterrupt]):
                with self.assertRaises(KeyboardInterrupt):
                    repair_one("qwen_base", SPEC, object())
            with patch("qc_eval.auto_repair.RUNS", root), patch("qc_eval.auto_repair.generate") as generate, patch(
                    "qc_eval.auto_repair.ensure_evaluation", return_value={"status": "completed"}):
                result = repair_one("qwen_base", SPEC, object())
                generate.assert_not_called()
            self.assertEqual(result["status"], "completed")


if __name__ == "__main__":
    unittest.main()
