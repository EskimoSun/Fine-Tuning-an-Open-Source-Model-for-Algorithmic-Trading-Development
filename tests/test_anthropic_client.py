"""Anthropic compatibility: deprecated sampling knobs and thinking blocks."""
import unittest
from unittest.mock import Mock, patch

from qc_eval.pipeline import call_fable


class AnthropicClientTests(unittest.TestCase):
    def test_modern_model_omits_temperature_and_extracts_only_answer_text(self):
        response = Mock()
        response.json.return_value = {"stop_reason": "end_turn", "content": [
            {"type": "thinking", "thinking": "internal", "signature": "opaque"},
            {"type": "text", "text": '{"score": 4}'}]}
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-only-key", "FABLE_MODEL": "claude-opus-5-5"}), patch(
                "qc_eval.pipeline.requests.post", return_value=response) as post:
            text = call_fable("Judge this", max_tokens=8192)
        payload = post.call_args[1]["json"]
        self.assertNotIn("temperature", payload)
        self.assertNotIn("thinking", payload)
        self.assertEqual(payload["max_tokens"], 8192)
        self.assertEqual(text, '{"score": 4}')

    def test_truncated_reply_is_not_returned_as_a_complete_judgment(self):
        response = Mock()
        response.json.return_value = {"stop_reason": "max_tokens", "content": [{"type": "text", "text": '{"score":'}]}
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-only-key"}), patch(
                "qc_eval.pipeline.requests.post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "reached max_tokens"):
                call_fable("Judge this")


if __name__ == "__main__":
    unittest.main()
