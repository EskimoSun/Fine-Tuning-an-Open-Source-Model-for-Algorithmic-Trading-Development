"""Offline scoring regression tests; no keys or cloud account required."""

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from qc_eval.behavior import (compare_behavior, dtw_distance, equity_points,
                              normalize_orders, timestamp)
from qc_eval.fidelity import DIMENSIONS, judge_request, parse_judgment
from qc_eval.qc_client import QCClient
from qc_eval.pipeline import ROOT, load_prompts, mock_generate
from qc_eval.score import digest, ensure_evaluation, format_progress, score_one, summarize


T = 1704196800  # 2024-01-02 UTC
CODE = "from AlgorithmImports import *\nclass Strategy(QCAlgorithm):\n    def initialize(self): pass\n"


def order(oid, qty=10, t=T, symbol="SPY", events=True):
    row = {"id": oid, "symbol": {"id": symbol, "value": symbol},
           "status": 3, "quantity": qty,
           "lastFillTime": "2024-01-02T12:00:00Z"}
    if events:
        row["events"] = [{"time": t, "fillQuantity": qty, "status": "filled"}]
    return row


def chart(values=(100, 101, 102), start=T):
    return {"series": {"Equity": {"values": [
        {"x": start + i * 86400, "y": v} for i, v in enumerate(values)]}}}


def run(orders=None, values=(100, 101, 102)):
    return {"status": "completed", "orders": [order(1)] if orders is None else orders,
            "equity_chart": chart(values)}


class BehaviorTests(unittest.TestCase):
    def test_identical_runs(self):
        result = compare_behavior(run(), run())
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["trade_matching"]["f1"], 1)
        self.assertEqual(result["equity"]["dtw_distance"], 0)
        self.assertEqual(result["position_direction_agreement"], 1)

    def test_wrong_asset_or_direction_cannot_match(self):
        for candidate in (order(1, symbol="QQQ"), order(1, qty=-10)):
            result = compare_behavior(run(), run([candidate]))
            self.assertEqual(result["trade_matching"]["f1"], 0)
            self.assertEqual(result["position_direction_agreement"], 0)

    def test_empty_runs_do_not_receive_perfect_trade_score(self):
        result = compare_behavior(run([]), run([]))
        self.assertIsNone(result["trade_matching"]["f1"])
        self.assertIsNone(result["trade_count"]["filled_order_relative_error"])
        self.assertIsNone(result["position_direction_agreement"])

    def test_no_trades_when_gold_trades(self):
        result = compare_behavior(run(), run([]))
        self.assertEqual(result["trade_matching"]["f1"], 0)
        self.assertEqual(result["trade_count"]["filled_order_relative_error"], 1)

    def test_simultaneous_legs_are_one_timestamp(self):
        rows = [order(1), order(2, -10, symbol="QQQ"), order(3, t=T + 3600)]
        result = compare_behavior(run(rows), run(rows))
        self.assertEqual(result["intervals"]["reference_median_seconds"], 3600)

    def test_partial_fills_are_counted_separately_from_orders(self):
        row = order(1)
        row["events"] = [{"time": T, "fillQuantity": 4}, {"time": T + 2, "fillQuantity": 6}]
        result = normalize_orders([row])
        self.assertEqual(result["filled_orders"], 1)
        self.assertEqual(result["fill_events"], 2)
        self.assertEqual(result["approximated_orders"], 0)

    def test_fallback_uses_last_fill_not_submission(self):
        row = order(1, events=False)
        row["time"] = "2020-01-01T00:00:00Z"
        result = normalize_orders([row])
        self.assertEqual(result["fills"][0]["time"], timestamp(row["lastFillTime"]))
        self.assertEqual(result["approximated_orders"], 1)

    def test_missing_partial_evidence_is_not_zero_trades(self):
        row = order(1, events=False)
        row["status"] = 5  # canceled after a partial fill
        result = compare_behavior(run(), run([row]))
        self.assertEqual(result["status"], "partial")
        self.assertNotIn("trade_count", result)

    def test_failed_reference_suppresses_behavior(self):
        result = compare_behavior({"status": "runtime_error"}, run())
        self.assertEqual(result["status"], "unavailable")

    def test_missing_equity_does_not_discard_trade_metrics(self):
        candidate = run()
        del candidate["equity_chart"]
        result = compare_behavior(run(), candidate)
        self.assertEqual(result["status"], "partial")
        self.assertIn("trade_count", result)

    def test_nonoverlapping_or_shorter_dates_not_compared(self):
        for start, values in ((T + 10 * 86400, (100, 101, 102)), (T, (100, 101))):
            candidate = run()
            candidate["equity_chart"] = chart(values, start)
            result = compare_behavior(run(), candidate)
            self.assertIsNone(result["equity"]["dtw_distance"])

    def test_candle_and_line_equity(self):
        candle = {"series": {"Equity": {"values": [{"x": T, "close": 100}]}}}
        self.assertEqual(equity_points(candle), [(float(T), 100)])

    def test_live_compact_equity_arrays_use_candle_close(self):
        for values in ([[T, 101]], [[T, 90, 120, 80, 101]]):
            compact = {"series": {"Equity": {"values": values}}}
            self.assertEqual(equity_points(compact), [(float(T), 101)])
        gold, candidate = run(), run()
        for result in (gold, candidate):
            result["equity_chart"] = {"series": {"Equity": {"values": [
                [T, 100, 100, 100, 100], [T + 86400, 100, 110, 95, 105],
                [T + 2 * 86400, 105, 112, 100, 110]]}}}
        metrics = compare_behavior(gold, candidate)
        self.assertEqual(metrics["status"], "available")
        self.assertEqual(metrics["equity"]["dtw_distance"], 0)

    def test_no_timezone_or_nonfinite_evidence(self):
        with self.assertRaises(ValueError):
            timestamp("2024-01-01T00:00:00")
        row = order(1)
        row["events"][0]["fillQuantity"] = float("nan")
        with self.assertRaises(ValueError):
            normalize_orders([row])

    def test_size_differences_visible_with_identical_trade_times(self):
        result = compare_behavior(run(), run([order(1, qty=20)]))
        self.assertEqual(result["trade_matching"]["mean_quantity_relative_error_matched_only"], 1)

    def test_dtw_and_unwarped_error_both_reported(self):
        result = compare_behavior(run(values=(100, 110, 110)), run(values=(100, 100, 110)))
        self.assertGreater(result["equity"]["same_date_return_mae"], result["equity"]["dtw_distance"])
        self.assertEqual(dtw_distance([0, 1, 2], [0, 1, 2]), 0)
        self.assertEqual(dtw_distance([0, 1], [0, 2], 0), 0.5)

    def test_closed_trades_are_distinct_from_filled_orders(self):
        gold, candidate = run(), run()
        gold["trade_statistics"] = {"totalNumberOfTrades": 2}
        candidate["raw_backtest"] = {"backtest": {"totalPerformance": {
            "tradeStatistics": {"totalNumberOfTrades": 3}}}}
        result = compare_behavior(gold, candidate)
        self.assertEqual(result["closed_trades"]["relative_error"], 0.5)
        self.assertEqual(result["trade_count"]["reference"]["filled_orders"], 1)

    def test_matching_is_one_to_one_and_tolerance_bound(self):
        result = compare_behavior(run([order(1), order(2, t=T + 10)]), run([order(1, t=T + 5)]))
        self.assertEqual(result["trade_matching"]["matched_fills"], 1)
        self.assertEqual(result["trade_matching"]["recall"], 0.5)
        late = compare_behavior(run(), run([order(1, t=T + 61)]), tolerance=60)
        self.assertEqual(late["trade_matching"]["matched_fills"], 0)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.client = QCClient("dummy-user", "dummy-token")

    def test_orders_fetches_all_pages(self):
        rows = [order(i) for i in range(105)]
        self.client._post = Mock(side_effect=[
            {"orders": rows[:100], "length": 105},
            {"orders": rows[100:], "length": 105},
            {"orders": [], "length": 105}])
        self.assertEqual(len(self.client.read_orders(1, "bt")), 105)
        self.assertEqual(self.client._post.call_args_list[1].args[1]["start"], 100)

    def test_loading_response_retried(self):
        self.client._post = Mock(side_effect=[{"status": "loading"}, {"chart": chart()}])
        with patch("qc_eval.qc_client.time.sleep"):
            self.assertEqual(self.client.read_equity_chart(1, "bt"), chart())

    def test_repeated_or_incomplete_pages_fail(self):
        for second in ([order(1)], []):
            self.client._post = Mock(side_effect=[{"orders": [order(1)], "length": 2},
                                                 {"orders": second, "length": 2}])
            with self.assertRaises(ValueError):
                self.client.read_orders(1, "bt")


class FidelityTests(unittest.TestCase):
    def judgment(self):
        return {"score": 5, "reason": "implements request", "needs_human_review": False,
                "template_conflicts": [],
                "dimensions": {d: {"requested": None, "status": "unspecified",
                                   "evidence": "Line 1: sensible default"} for d in DIMENSIONS}}

    def test_valid_judgment_and_uncertainty(self):
        obj = self.judgment()
        self.assertEqual(parse_judgment(json.dumps(obj))["score"], 5)
        obj["score"] = 3
        obj["dimensions"]["assets"]["status"] = "uncertain"
        self.assertTrue(parse_judgment(json.dumps(obj))["needs_human_review"])

    def test_invalid_or_contradictory_judge_scores(self):
        for value in (True, 0, 6, "5", 4.2):
            obj = self.judgment()
            obj["score"] = value
            with self.assertRaises(ValueError):
                parse_judgment(json.dumps(obj))
        obj = self.judgment()
        obj["dimensions"]["assets"]["status"] = "key_mismatch"
        with self.assertRaises(ValueError):
            parse_judgment(json.dumps(obj))

    def test_vague_prompt_is_authority_over_gold(self):
        request = judge_request({"prompt": "trade RSI", "specificity": "vague"}, CODE, CODE)
        self.assertIn("template is an example, not the", request)
        self.assertIn("do not penalize choices the request left open", request)
        self.assertIn("Do not lower fidelity solely for compilation/runtime failure", request)


class ScoringTests(unittest.TestCase):
    def test_end_to_end_reuses_gold_and_invalidates_changed_judge_input(self):
        spec = load_prompts()[0]
        reference = (ROOT / spec["reference_path"]).read_text()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            gold_path = output / "evaluations/gold" / (spec["template_id"] + ".json")
            gold_path.parent.mkdir(parents=True)
            gold = run()
            gold["source_sha256"] = digest(reference)
            gold_path.write_text(json.dumps(gold))
            candidate = run()
            candidate["source_sha256"] = digest(CODE)
            record = {"output": CODE, "model_id": "test-model", "qc_evaluation": candidate}
            args = argparse.Namespace(output_dir=output, judge=True, rejudge=False,
                                      rerun_qc=False, gold_refreshed=set(),
                                      time_tolerance_seconds=60, dtw_window=1)
            with patch.dict("os.environ", {"FABLE_MODEL": "test-judge"}), patch(
                    "qc_eval.score.judge_fidelity", return_value={"status": "judged", "score": 4}) as judge:
                first = score_one("qwen_base", spec, record, args, None)
                self.assertEqual(first["behavior"]["status"], "available")
                self.assertEqual(first["fidelity"]["score"], 4)
                score_one("qwen_base", spec, record, args, None)
                self.assertEqual(judge.call_count, 1)
                changed_spec = dict(spec, prompt=spec["prompt"] + " Also hold GLD.")
                score_one("qwen_base", changed_spec, record, args, None)
                self.assertEqual(judge.call_count, 2)

    def test_generation_skip_judge_does_not_call_model_judge(self):
        from qc_eval.pipeline import process
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(regenerate=False, mock=False, skip_judge=True,
                                      rerun_qc=False, rejudge=False)
            spec = load_prompts()[0]
            with patch("qc_eval.pipeline.RUNS", Path(tmp)), patch(
                    "qc_eval.pipeline.generate", return_value=(mock_generate("test"), "test")), patch(
                    "qc_eval.pipeline.judge") as judge:
                result = process("qwen_base", spec, args, None)
                self.assertTrue(result["has_code"])
                judge.assert_not_called()

    def test_real_generation_replaces_mock_but_preserves_existing_baseline(self):
        from qc_eval.pipeline import process
        spec = load_prompts()[0]
        args = argparse.Namespace(regenerate=False, mock=False, skip_judge=True,
                                  rerun_qc=False, rejudge=False)
        for cached_model in ("mock", "real-model"):
            with self.subTest(cached_model=cached_model), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "qwen_base" / (spec["id"] + ".json")
                path.parent.mkdir()
                original = {"model_id": cached_model, "output": CODE,
                            "generated_at": "original-time"}
                path.write_text(json.dumps(original))
                with patch("qc_eval.pipeline.RUNS", Path(tmp)), patch(
                        "qc_eval.pipeline.generate", return_value=(mock_generate("test"), "real-model")) as generate:
                    result = process("qwen_base", spec, args, None)
                self.assertEqual(result["model_id"], "real-model")
                if cached_model == "mock":
                    generate.assert_called_once()
                    self.assertNotEqual(result["output"], CODE)
                else:
                    generate.assert_not_called()
                    self.assertEqual(result["output"], CODE)
                    self.assertEqual(result["generated_at"], "original-time")

    def test_evidence_reused_only_for_same_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cached.json"
            old = {"source_sha256": digest("wrong code"), "status": "completed"}
            path.write_text(json.dumps(old))
            result = ensure_evaluation(CODE, path, "test")
            self.assertEqual(result["status"], "not_run")

    def test_completed_seed_avoids_new_cloud_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = Mock()
            seed = run()
            seed.update(source_sha256=digest(CODE), project_id=1, backtest_id="bt")
            result = ensure_evaluation(CODE, Path(tmp) / "cache.json", "test", client, seed)
            self.assertEqual(result["status"], "completed")
            client.create_project.assert_not_called()
            client.read_orders.assert_not_called()

    def test_failed_execution_is_cached_until_explicit_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = Mock()
            seed = {"source_sha256": digest(CODE), "status": "runtime_error"}
            result = ensure_evaluation(CODE, Path(tmp) / "cache.json", "test", client, seed)
            self.assertEqual(result["status"], "runtime_error")
            client.create_project.assert_not_called()

    def test_mock_generations_never_sent_to_cloud_or_judge(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(output_dir=Path(tmp), judge=True)
            spec = {"id": "test", "prompt": "trade", "template_id": "rsi"}
            client = Mock()
            result = score_one("qwen_base", spec, {"model_id": "mock"}, args, client)
            self.assertEqual(result["status"], "mock_generation")
            self.assertIsNone(result["fidelity"]["score"])
            client.create_project.assert_not_called()

    def test_missing_scores_do_not_become_zero(self):
        results = [{"prompt_id": "a", "model": "qwen_base", "status": "scored", "fidelity": {"score": 5}},
                   {"prompt_id": "b", "model": "qwen_base", "status": "missing_generation", "fidelity": {"score": None}}]
        summary = summarize(results)["all"]
        self.assertEqual(summary["fidelity_mean"], 5)
        self.assertEqual(summary["rows_with_fidelity"], 1)
        self.assertEqual(summary["requested_rows"], 2)

    def test_failed_execution_visible_even_when_report_was_scored(self):
        result = {"prompt_id": "a", "model": "qwen_base", "status": "scored",
                  "fidelity": {"status": "not_judged", "score": None},
                  "execution": {"reference": {"status": "completed"},
                                "candidate": {"status": "runtime_error", "qc_note": "Resolution has no attribute &#039;Hourly&#039;"}},
                  "behavior": {"status": "unavailable", "errors": ["candidate backtest did not complete successfully"]}}
        output = format_progress(result)
        self.assertIn("candidate=runtime_error", output)
        self.assertIn("reference=completed", output)
        self.assertIn("'Hourly'", output)
        summary = summarize([result])["all"]
        self.assertEqual(summary["candidate_execution_statuses"], {"runtime_error": 1})
        self.assertEqual(summary["behavior_statuses"], {"unavailable": 1})


if __name__ == "__main__":
    unittest.main()
