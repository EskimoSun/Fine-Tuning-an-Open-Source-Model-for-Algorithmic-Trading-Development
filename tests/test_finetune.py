"""Training-set builder: chat format, no test-set leakage, template-level validation split."""

import json
import tempfile
import unittest
from pathlib import Path

from finetune import build_dataset as bd
from qc_eval.pipeline import SYSTEM, load_prompts


class BuildDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.manifest = bd.main(["--out", cls.tmp.name])
        cls.rows = []
        for name in ("train", "val"):
            with open(Path(cls.tmp.name) / (name + ".jsonl"), encoding="utf-8") as f:
                cls.rows += [json.loads(line) for line in f]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_chat_format(self):
        self.assertTrue(self.rows)
        for r in self.rows:
            roles = [m["role"] for m in r["messages"]]
            self.assertEqual(roles, ["system", "user", "assistant"])
            system, answer = r["messages"][0]["content"], r["messages"][2]["content"]
            if system == SYSTEM:
                self.assertTrue(answer.startswith("```python\n") and answer.endswith("\n```"))
                self.assertIn("from AlgorithmImports import *", answer)
            else:
                self.assertEqual(system, bd.FAQ_SYSTEM)

    def test_no_eval_templates_or_prompts(self):
        eval_codes = [p.read_text(encoding="utf-8").strip() for p in bd.EVAL_TEMPLATES.glob("*/main.py")]
        eval_prompts = {p["prompt"] for p in load_prompts()}
        self.assertEqual(len(eval_codes), 10)
        for r in self.rows:
            self.assertNotIn(r["messages"][1]["content"], eval_prompts)
            for code in eval_codes:
                self.assertNotIn(code, r["messages"][2]["content"])
        self.assertFalse(set(bd.load_template_codes()) & bd.eval_folders())
        self.assertLessEqual(self.manifest["max_code_sim_kept"], bd.CODE_SIM_MAX)

    def test_validation_split_holds_out_whole_templates(self):
        val = set(self.manifest["val_templates"])
        self.assertTrue(val)
        rows, _ = bd.template_examples(bd.load_template_codes(), bd.load_meta())
        train_templates = {r["template_id"] for r in rows if not bd.is_val(r["template_id"], 0.1)}
        self.assertFalse(val & train_templates)

    def test_handwritten_prompts_parse(self):
        rows = bd.load_prompt_rows()
        self.assertGreater(len(rows), 100)
        self.assertFalse({r["template_id"] for r in rows} & bd.eval_folders())

    def test_faq_drops_pascal_aliases_and_links(self):
        for r in bd.faq_examples():
            self.assertNotRegex(r["answer"], r"\(`[A-Z][A-Za-z0-9]*`\)")
            self.assertNotIn("Docs: <", r["answer"])


if __name__ == "__main__":
    unittest.main()
