"""Check visible evidence, real-output enforcement and transient request retries."""

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from qc_eval.pipeline import call_openai_compatible, load_prompts, process
from qc_eval.reporting import QCProgressPrinter, print_execution
from qc_eval.score import main


CODE = "class RealStrategy(QCAlgorithm):\n    def initialize(self):\n        pass\n"


class ReportingTests(unittest.TestCase):
    def test_saved_real_code_is_printed_without_regeneration(self):
        spec = load_prompts()[0]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "qwen_base" / (spec["id"] + ".json")
            path.parent.mkdir()
            path.write_text(json.dumps({"model_id": "real-qwen", "output": CODE}))
            args = argparse.Namespace(mock=False, regenerate=False, print_output=True,
                                      skip_judge=True, rerun_qc=False, rejudge=False)
            output = io.StringIO()
            with patch("qc_eval.pipeline.RUNS", Path(tmp)), patch("qc_eval.pipeline.generate") as generate, redirect_stdout(output):
                process("qwen_base", spec, args, None)
            generate.assert_not_called()
            self.assertIn(CODE, output.getvalue())
            self.assertIn("mock=False", output.getvalue())
            self.assertIn("source=saved_generation", output.getvalue())

    def test_qc_stage_and_actual_statistics_are_printed(self):
        output = io.StringIO()
        with redirect_stdout(output):
            reporter = QCProgressPrinter("real-run")
            record = {"stage": "backtest", "status": "running", "project_id": 123,
                      "backtest_id": "actual-id", "raw_backtest": {"backtest": {
                          "status": "Running", "progress": 0.25}}, "Authorization": "never-print-this"}
            reporter(record)
            reporter(record)  # unchanged polls should not flood the console
            print_execution("real-run", {"status": "completed", "statistics": {"Total Orders": "12"},
                                         "logs": ["actual engine log"], "Authorization": "never-print-this"})
        text = output.getvalue()
        self.assertEqual(text.count("progress=25.0%"), 1)
        self.assertIn('"Total Orders": "12"', text)
        self.assertIn("actual engine log", text)
        self.assertNotIn("never-print-this", text)

    def test_require_real_stops_before_any_cloud_authentication(self):
        spec = load_prompts()[0]
        for mock in (False, True):
            with self.subTest(mock=mock), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                if mock:
                    path = root / "qwen_base" / (spec["id"] + ".json")
                    path.parent.mkdir()
                    path.write_text(json.dumps({"model_id": "mock", "output": CODE}))
                with patch("qc_eval.score.RUNS", root), patch("qc_eval.qc_client.QCClient") as client, patch(
                        "sys.argv", ["score", "--limit", "1", "--qc", "--require-real"]), redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        main()
                    self.assertEqual(error.exception.code, 2)
                    client.assert_not_called()


class RequestRetryTests(unittest.TestCase):
    def test_rate_limited_request_retries_without_fake_output(self):
        limited = Mock(status_code=429, headers={"Retry-After": "1"})
        success = Mock(status_code=200)
        success.json.return_value = {"choices": [{"message": {"content": CODE}}]}
        with patch.dict("os.environ", {"QWEN_BASE_URL": "https://example.invalid/v1", "QWEN_API_KEY": "test-key"}), patch(
                "qc_eval.pipeline.requests.post", side_effect=[limited, success]) as post, patch(
                "qc_eval.pipeline.time.sleep") as sleep, redirect_stdout(io.StringIO()):
            result = call_openai_compatible("real request", "real-qwen")
        self.assertEqual(result, CODE)
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_long_quota_wait_is_reported_instead_of_returning_mock(self):
        limited = Mock(status_code=429, headers={"Retry-After": "86400"})
        limited.raise_for_status.side_effect = requests.HTTPError("quota exhausted")
        with patch.dict("os.environ", {"QWEN_BASE_URL": "https://example.invalid/v1", "QWEN_API_KEY": "test-key"}), patch(
                "qc_eval.pipeline.requests.post", return_value=limited) as post, patch(
                "qc_eval.pipeline.time.sleep") as sleep:
            with self.assertRaises(requests.HTTPError):
                call_openai_compatible("real request", "real-qwen")
        post.assert_called_once()
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
