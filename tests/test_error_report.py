"""Offline regression tests for error_report's classification rules."""

import unittest

from qc_eval.error_report import aggregate, classify, generalization_gap


def row(status, error_cause=None, error=None, decline_text=None, **extra):
    return dict(candidate_status=status, error_cause=error_cause, error=error,
                decline_text=decline_text, **extra)


class ClassifyTests(unittest.TestCase):
    def test_completed_is_not_a_failure(self):
        self.assertIsNone(classify(row("completed")))

    def test_status_wins_over_error_text(self):
        self.assertEqual(classify(row("not_generated")), "not_generated")
        self.assertEqual(classify(row("no_code", decline_text="can't do this")), "declined_no_code")
        self.assertEqual(classify(row("runtime_error", decline_text="nope")), "declined_no_code")
        self.assertEqual(classify(row("infrastructure_error", error_cause="'NoneType' object has no attribute 'get'")),
                          "pending_infrastructure_error")

    def test_missing_attribute_phrasing_variants(self):
        self.assertEqual(classify(row("runtime_error", error_cause="'TimeRules' object has no attribute 'every_minute'")),
                          "missing_attribute_or_api")
        self.assertEqual(classify(row("runtime_error", error="type object 'Resolution' has no attribute 'Hourly'")),
                          "missing_attribute_or_api")

    def test_null_reference_not_confused_with_missing_attribute(self):
        self.assertEqual(classify(row("runtime_error", error_cause="Object reference not set to an instance of an object.")),
                          "null_reference")

    def test_api_argument_mismatch(self):
        self.assertEqual(classify(row("runtime_error", error_cause="Argument mismatch: argument 3 expected bool, got int.")),
                          "api_argument_mismatch")

    def test_undefined_symbol(self):
        self.assertEqual(classify(row("runtime_error", error_cause="name 'rsi' is not defined")), "undefined_symbol")

    def test_python_exception(self):
        self.assertEqual(classify(row("runtime_error", error_cause="The key 'SPY' was not found in the collection")),
                          "python_exception")

    def test_unrecognized_runtime_error_falls_back(self):
        self.assertEqual(classify(row("runtime_error", error_cause="something nobody has seen before")),
                          "other_runtime_error")

    def test_error_cause_takes_priority_over_raw_error(self):
        self.assertEqual(classify(row("runtime_error", error_cause="name 'rsi' is not defined",
                                       error="a much longer raw traceback with no clean cause")),
                          "undefined_symbol")


class AggregateTests(unittest.TestCase):
    def test_generalization_gap_flags_overfit_prompt_engineering(self):
        rows = ([row("completed", run="v3", split="tuned_on")] * 6
                + [row("runtime_error", error_cause="name 'rsi' is not defined", run="v3", split="tuned_on")] * 4
                + [row("completed", run="v3", split="held_out")] * 11
                + [row("runtime_error", error_cause="name 'rsi' is not defined", run="v3", split="held_out")] * 79)
        agg = aggregate(rows)
        gap = generalization_gap(agg["by_run"]["v3"])
        self.assertAlmostEqual(gap["tuned_on_rate"], 0.6)
        self.assertAlmostEqual(gap["held_out_rate"], 11 / 90, places=3)
        self.assertFalse(gap["generalizes"])


if __name__ == "__main__":
    unittest.main()
