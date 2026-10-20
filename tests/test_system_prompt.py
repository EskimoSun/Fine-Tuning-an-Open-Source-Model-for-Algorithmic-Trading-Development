"""The --system flag picks the system prompt and keeps v2 runs in their own cache."""

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import os

from qc_eval.pipeline import SYSTEM, SYSTEM_PROMPTS, SYSTEM_V2, SYSTEM_V3, generate, load_prompts, process, run_label


class SystemPromptTests(unittest.TestCase):
    def test_versions_extend_v1_without_test_prompts(self):
        for text in (SYSTEM_V2, SYSTEM_V3):
            self.assertTrue(text.startswith(SYSTEM))
            self.assertIn("from AlgorithmImports import *", text)
            for spec in load_prompts():
                self.assertNotIn(spec["prompt"], text)
        self.assertIn("BY KEYWORD", SYSTEM_V3)

    def test_prompt_version_label_uses_base_model(self):
        env = {"QWEN_BASE_MODEL": "base-id", "QWEN_TUNED_MODEL": "tuned-id"}
        with patch.dict(os.environ, env), \
                patch("qc_eval.pipeline.call_openai_compatible", return_value="out") as call:
            self.assertEqual(generate("qwen_base_prompt_v3", "p")[1], "base-id")
            self.assertEqual(call.call_args.args[1], "base-id")
            self.assertEqual(generate("qwen_tuned", "p")[1], "tuned-id")

    def test_labels(self):
        self.assertEqual(run_label("qwen_base"), "qwen_base")
        self.assertEqual(run_label("qwen_base", "v2"), "qwen_base_prompt_v2")
        self.assertEqual(run_label("qwen_base", "v3"), "qwen_base_prompt_v3")

    def test_v2_generation_uses_v2_prompt_and_cache(self):
        spec = load_prompts()[0]
        args = argparse.Namespace(mock=False, regenerate=False, print_output=False, skip_judge=True,
                                  rerun_qc=False, rejudge=False, system="v2")
        with tempfile.TemporaryDirectory() as tmp, \
                patch("qc_eval.pipeline.RUNS", Path(tmp)), \
                patch("qc_eval.pipeline.generate", return_value=("no code", "qwen-x")) as generate:
            process("qwen_base", spec, args, None)
            self.assertIs(generate.call_args.kwargs["system"], SYSTEM_PROMPTS["v2"])
            path = Path(tmp) / "qwen_base_prompt_v2" / (spec["id"] + ".json")
            rec = json.loads(path.read_text())
            self.assertEqual(rec["system_prompt"], "v2")
            self.assertFalse((Path(tmp) / "qwen_base").exists())


if __name__ == "__main__":
    unittest.main()
