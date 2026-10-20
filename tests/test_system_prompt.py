"""The --system flag picks the system prompt and keeps v2 runs in their own cache."""

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qc_eval.pipeline import SYSTEM, SYSTEM_PROMPTS, SYSTEM_V2, load_prompts, process, run_label


class SystemPromptTests(unittest.TestCase):
    def test_v2_extends_v1_without_test_prompts(self):
        self.assertTrue(SYSTEM_V2.startswith(SYSTEM))
        self.assertIn("from AlgorithmImports import *", SYSTEM_V2)
        for spec in load_prompts():
            self.assertNotIn(spec["prompt"], SYSTEM_V2)

    def test_labels(self):
        self.assertEqual(run_label("qwen_base"), "qwen_base")
        self.assertEqual(run_label("qwen_base", "v2"), "qwen_base_prompt_v2")

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
