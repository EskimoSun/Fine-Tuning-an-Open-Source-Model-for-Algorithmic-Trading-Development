"""Deterministic template-similarity diagnostics. No model calls or network.

These measurements are deliberately NOT converted into a 1-5 fidelity grade.
An underspecified prompt need not reproduce a template's exact trades.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean, median


def timestamp(value):
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("Execution timestamps must include a timezone")
        result = dt.timestamp()
    if not math.isfinite(result):
        raise ValueError("Non-finite timestamp")
    return result


def number(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Non-finite numeric evidence")
    return value


def normalize_orders(rows):
    """Prefer actual partial-fill events over order submission timestamps.

    With no events, a fully filled order can be approximated at lastFillTime.
    Partial/canceled filled orders without event quantities are unscorable.
    Stable security IDs distinguish option strikes and futures contracts.
    """
    fills, filled_orders, approximated = [], 0, 0
    for wrapper in rows:
        order = wrapper.get("order", wrapper)
        symbol = order.get("symbol", {})
        if isinstance(symbol, dict):
            sid = symbol.get("id") or symbol.get("value")
            label = symbol.get("value", sid)
        else:
            sid = label = symbol
        if not sid:
            raise ValueError("Order has no symbol")
        events = order.get("events", wrapper.get("events", [])) or []
        executed = []
        for event in events:
            qty = number(event.get("fillQuantity", 0))
            if qty:
                executed.append({"time": timestamp(event["time"]),
                                 "quantity": qty, "symbol": sid, "label": label,
                                 "order_id": order["id"]})
        status = str(order.get("status", "")).lower()
        if not executed and status in ("3", "filled"):
            if not order.get("lastFillTime"):
                raise ValueError("Filled order has neither fill events nor lastFillTime")
            qty = number(order["quantity"])
            if qty == 0:
                raise ValueError("Filled order has zero quantity")
            executed = [{"time": timestamp(order["lastFillTime"]),
                         "quantity": qty, "symbol": sid, "label": label,
                         "order_id": order["id"]}]
            approximated += 1
        elif not executed and (status in ("2", "partiallyfilled") or order.get("lastFillTime")):
            raise ValueError("Partially filled order is missing fill-event evidence")
        if executed:
            filled_orders += 1
            fills.extend(executed)
    return {"fills": sorted(fills, key=lambda f: (f["time"], str(f["symbol"]))),
            "submitted_orders": len(rows), "filled_orders": filled_orders,
            "fill_events": len(fills), "approximated_orders": approximated}


def equity_points(chart):
    series = chart.get("series", {})
    if isinstance(series, list):
        series = {s["name"]: s for s in series}
    if series.get("name") == "Equity":
        equity = series
    else:
        equity = series.get("Equity")
    if equity is None:
        raise ValueError("Strategy Equity chart has no Equity series")
    values = equity.get("values", [])
    if isinstance(values, dict):
        values = list(values.values())
    result = {}
    for point in values:
        # QC cloud also serializes compact arrays: [x,y] for lines and
        # [x,open,high,low,close] for candles. Live evidence uses this shape.
        if isinstance(point, (list, tuple)):
            if len(point) not in (2, 5):
                raise ValueError("Unsupported compact equity point length: " + str(len(point)))
            x, value = point[0], point[-1]
        else:
            x = point["x"]
            value = point["y"] if "y" in point else point["close"]
        result[timestamp(x)] = number(value)
    if not result:
        raise ValueError("Equity series is empty")
    return sorted(result.items())


def dtw_distance(a, b, window=1):
    """Absolute-cost DTW, divided by selected path length; O(n*window) space/time.

    A bounded Sakoe-Chiba band prevents unlimited time shifting. No z-scoring:
    leverage/magnitude differences must remain visible in cumulative returns.
    """
    if window < 0:
        raise ValueError("DTW window must be nonnegative")
    if not a or not b or abs(len(a) - len(b)) > window:
        return None
    previous = {0: (0.0, 0)}
    for i, x in enumerate(a, 1):
        current = {}
        for j in range(max(1, i - window), min(len(b), i + window) + 1):
            choices = [previous.get(j), current.get(j - 1), previous.get(j - 1)]
            choices = [c for c in choices if c is not None]
            if choices:
                cost, length = min(choices, key=lambda c: (c[0], c[1]))
                current[j] = (cost + abs(x - b[j - 1]), length + 1)
        previous = current
    cost, length = previous[len(b)]
    return cost / length


def _daily(points):
    daily = {}
    for t, value in points:
        daily[datetime.fromtimestamp(t, timezone.utc).date().isoformat()] = value
    return daily


def equity_metrics(reference, candidate, window=1):
    gold, generated = _daily(reference), _daily(candidate)
    common = sorted(gold.keys() & generated.keys())
    union = gold.keys() | generated.keys()
    coverage = len(common) / len(union) if union else 0
    result = {"frequency": "last available value per UTC day",
              "reference_days": len(gold), "candidate_days": len(generated),
              "common_days": len(common), "date_coverage": coverage,
              "reference_date_range": [min(gold), max(gold)] if gold else None,
              "candidate_date_range": [min(generated), max(generated)] if generated else None,
              "dtw_window_observations": window,
              "dtw_distance": None, "same_date_return_mae": None}
    if len(common) < 2 or coverage < 0.95 or min(gold) != min(generated) or max(gold) != max(generated):
        result["unavailable_reason"] = "Need matching date ranges and >=95% common daily observations"
        return result
    ga, ca = gold[common[0]], generated[common[0]]
    if ga <= 0 or ca <= 0:
        result["unavailable_reason"] = "Initial equity must be positive"
        return result
    a = [gold[d] / ga - 1 for d in common]
    b = [generated[d] / ca - 1 for d in common]
    result.update(dtw_distance=dtw_distance(a, b, window),
                  same_date_return_mae=mean(abs(x - y) for x, y in zip(a, b)),
                  final_return_absolute_difference=abs(a[-1] - b[-1]))
    return result


def _intervals(fills):
    times = sorted(set(f["time"] for f in fills))
    return [b - a for a, b in zip(times, times[1:])]


def _quantile(values, p):
    index = p * (len(values) - 1)
    low, high = math.floor(index), math.ceil(index)
    return values[low] + (values[high] - values[low]) * (index - low)


def _match_fills(gold, candidate, tolerance):
    groups = [defaultdict(list), defaultdict(list)]
    for fills, grouped in zip((gold, candidate), groups):
        for f in fills:
            grouped[(f["symbol"], f["quantity"] > 0)].append(f)
    matches, lags, qty_errors = 0, [], []
    for key in groups[0].keys() | groups[1].keys():
        a, b = groups[0][key], groups[1][key]
        i = j = 0
        while i < len(a) and j < len(b):
            lag = b[j]["time"] - a[i]["time"]
            if lag < -tolerance:
                j += 1
            elif lag > tolerance:
                i += 1
            else:
                matches += 1
                lags.append(abs(lag))
                qty_errors.append(abs(b[j]["quantity"] - a[i]["quantity"]) / abs(a[i]["quantity"]))
                i, j = i + 1, j + 1
    # Two empty trade streams provide no evidence of implementing a strategy.
    precision = matches / len(candidate) if candidate else (0.0 if gold else None)
    recall = matches / len(gold) if gold else None
    f1 = 2 * matches / (len(gold) + len(candidate)) if gold or candidate else None
    return {"matched_fills": matches, "precision": precision, "recall": recall,
            "f1": f1, "time_tolerance_seconds": tolerance,
            "mean_absolute_timing_error_seconds": mean(lags) if lags else None,
            "mean_quantity_relative_error_matched_only": mean(qty_errors) if qty_errors else None}


def _direction_agreement(gold, candidate, end_time):
    """Time-weighted per-security long/flat/short agreement from cumulative fills.

    Only intervals with at least one non-flat security count, so long periods
    where both algorithms do nothing cannot dominate the measurement.
    """
    events = defaultdict(list)
    for side, fills in enumerate((gold, candidate)):
        for f in fills:
            events[f["time"]].append((side, f["symbol"], f["quantity"]))
    positions = [defaultdict(float), defaultdict(float)]
    times = sorted(set(events) | {end_time})
    matched = total = 0.0
    for i, t in enumerate(times[:-1]):
        for side, symbol, qty in events[t]:
            positions[side][symbol] += qty
        duration = max(0, times[i + 1] - t)
        for symbol in positions[0].keys() | positions[1].keys():
            a, b = positions[0][symbol], positions[1][symbol]
            sa = 0 if abs(a) < 1e-8 else (1 if a > 0 else -1)
            sb = 0 if abs(b) < 1e-8 else (1 if b > 0 else -1)
            if sa or sb:
                total += duration
                matched += duration * (sa == sb)
    return matched / total if total else None


def compare_behavior(reference, candidate, tolerance=60, dtw_window=1):
    """Inputs are QC evaluation subrecords including orders and equity_chart."""
    if tolerance < 0 or dtw_window < 0:
        raise ValueError("Comparison tolerances must be nonnegative")
    result = {"status": "unavailable", "errors": []}
    for name, run in (("reference", reference), ("candidate", candidate)):
        if run.get("status") != "completed":
            result["errors"].append(name + " backtest did not complete successfully")
    if result["errors"]:
        return result
    result["status"] = "partial"
    def closed_trades(run):
        stats = run.get("trade_statistics")
        if stats is None:
            stats = run.get("raw_backtest", {}).get("backtest", {}).get("totalPerformance", {}).get("tradeStatistics", {})
        count = stats.get("totalNumberOfTrades")
        return int(count) if count is not None else None
    gc, cc = closed_trades(reference), closed_trades(candidate)
    result["closed_trades"] = {"reference": gc, "candidate": cc,
                               "relative_error": abs(cc - gc) / gc if gc and cc is not None else None}
    try:
        ga = normalize_orders(reference["orders"])
        ca = normalize_orders(candidate["orders"])
        result["trade_count"] = {
            "definition": "filled orders; fill events also counted; neither is a closed round trip",
            "reference": {k: v for k, v in ga.items() if k != "fills"},
            "candidate": {k: v for k, v in ca.items() if k != "fills"},
            "filled_order_relative_error": abs(ca["filled_orders"] - ga["filled_orders"]) / ga["filled_orders"] if ga["filled_orders"] else None}
        gf, cf = ga["fills"], ca["fills"]
        result["trade_matching"] = _match_fills(gf, cf, tolerance)
        gs, cs = sorted({f["symbol"] for f in gf}), sorted({f["symbol"] for f in cf})
        result["assets"] = {"reference": gs, "candidate": cs,
                            "jaccard": len(set(gs) & set(cs)) / len(set(gs) | set(cs)) if gs or cs else None}
        gi, ci = sorted(_intervals(gf)), sorted(_intervals(cf))
        result["intervals"] = {"definition": "elapsed UTC seconds between distinct fill timestamps; simultaneous legs grouped",
                               "reference_median_seconds": median(gi) if gi else None,
                               "candidate_median_seconds": median(ci) if ci else None,
                               "quantile_mae_seconds": mean(abs(_quantile(gi, p / 100) - _quantile(ci, p / 100)) for p in range(101)) if gi and ci else None}
    except (KeyError, ValueError, TypeError) as exc:
        result["errors"].append("order evidence: " + str(exc))
        gf = cf = None
    try:
        gp, cp = equity_points(reference["equity_chart"]), equity_points(candidate["equity_chart"])
        result["equity"] = equity_metrics(gp, cp, dtw_window)
        if result["equity"].get("unavailable_reason"):
            result["errors"].append(result["equity"]["unavailable_reason"])
        elif gf is not None:
            end = min(gp[-1][0], cp[-1][0])
            if all(f["time"] <= end for f in gf + cf):
                result["position_direction_agreement"] = _direction_agreement(gf, cf, end)
            else:
                result["errors"].append("Equity evidence ends before the last fill")
    except (KeyError, ValueError, TypeError) as exc:
        result["errors"].append("equity evidence: " + str(exc))
    if not result["errors"]:
        result["status"] = "available"
    return result
