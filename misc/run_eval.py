"""
Score model outputs.

Input:  a JSONL file, one line per generation:
        {"prompt_id": "eq_sma_cross", "model": "qwen2.5-coder-7b", "output": "<raw model text>"}
Output: results.csv (one row per generation) and a per-model summary
        printed to the terminal.

Usage:
    python -m qc_eval.run_eval generations.jsonl                 # static only
    python -m qc_eval.run_eval generations.jsonl --backtest      # + QC cloud
"""

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from ..src.qc_eval.static_checks import extract_code, run_static_checks
from ..src.qc_eval.taxonomy import Finding

HERE = Path(__file__).parent
PROMPTS_FILE = HERE.parent / "prompts.jsonl"

ABSTAIN_MARKERS = ("i'm not sure", "i am not sure", "cannot determine", "i can't", "i cannot")


def load_prompts(path: Path = PROMPTS_FILE) -> dict:
    with open(path) as f:
        return {p["id"]: p for p in map(json.loads, f) if p}


def score_one(gen: dict, prompts: dict, qc=None) -> dict:
    spec = prompts.get(gen["prompt_id"])
    output = gen["output"]
    code = extract_code(output)

    findings: list[Finding] = []
    if code is None:
        lowered = output.lower()
        code_ = "ABSTAINED" if any(m in lowered for m in ABSTAIN_MARKERS) else "NO_CODE"
        findings.append(Finding(code_))
    else:
        findings = run_static_checks(code, spec)

    if spec and spec.get("category") == "abstention":
        # For these prompts the correct behavior is to flag the problem.
        # Heuristic: pass only if the model abstained. Hand-check a sample.
        static_pass = any(f.code == "ABSTAINED" for f in findings)
    else:
        static_pass = code is not None and not any(
            f.category.severity == "fail" for f in findings)

    row = {
        "prompt_id": gen["prompt_id"],
        "model": gen["model"],
        "static_pass": static_pass,
        "compiled": None,
        "ran": None,
        "total_orders": None,
        "findings": findings,
    }

    # Cloud stages only for code that passed static checks
    if qc is not None and static_pass:
        project_id = qc.create_project(f"eval-{gen['model']}-{gen['prompt_id']}")
        qc.update_main(project_id, code)
        ok, compile_id, logs = qc.compile(project_id)
        row["compiled"] = ok
        if not ok:
            findings.append(Finding("COMPILE_ERROR", " | ".join(map(str, logs))[:300]))
        else:
            bt = qc.backtest(project_id, compile_id, gen["prompt_id"])
            row["ran"] = bt["status"] == "completed"
            if bt["status"] == "runtime_error":
                findings.append(Finding("RUNTIME_ERROR", str(bt.get("error"))[:300]))
            elif bt["status"] == "timeout":
                findings.append(Finding("TIMEOUT"))
            else:
                orders = bt.get("total_orders")
                row["total_orders"] = orders
                if spec and spec.get("expects_orders", True) and str(orders) in ("0", "None"):
                    findings.append(Finding("NO_TRADES"))
    return row


def bootstrap_ci(values: list[bool], n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    """95% bootstrap interval for a pass rate."""
    if not values:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choices(values, k=n)) / n for _ in range(n_boot))
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot)]


def summarize(rows: list[dict]) -> None:
    by_model = defaultdict(list)
    for r in rows:
        by_model[r["model"]].append(r)

    for model, rs in sorted(by_model.items()):
        passes = [r["static_pass"] for r in rs]
        rate = sum(passes) / len(passes)
        lo, hi = bootstrap_ci(passes)
        print(f"\n=== {model}  (n={len(rs)}) ===")
        print(f"static pass rate: {rate:.0%}  [95% CI {lo:.0%}-{hi:.0%}]")
        if any(r["compiled"] is not None for r in rs):
            comp = [bool(r["compiled"]) for r in rs]
            ran = [bool(r["ran"]) for r in rs]
            print(f"compile rate:     {sum(comp)/len(comp):.0%}")
            print(f"run rate:         {sum(ran)/len(ran):.0%}")
        counts = Counter(f.code for r in rs for f in r["findings"])
        for code, n in counts.most_common():
            print(f"  {code:<20} {n}")


def write_csv(rows: list[dict], path: Path) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["prompt_id", "model", "static_pass", "compiled", "ran",
                    "total_orders", "finding_codes", "finding_details"])
        for r in rows:
            w.writerow([r["prompt_id"], r["model"], r["static_pass"], r["compiled"],
                        r["ran"], r["total_orders"],
                        ";".join(f.code for f in r["findings"]),
                        " || ".join(f"{f.code}: {f.detail}" for f in r["findings"] if f.detail)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("generations", type=Path)
    ap.add_argument("--backtest", action="store_true",
                    help="also compile and backtest on QuantConnect (needs QC_USER_ID / QC_API_TOKEN)")
    ap.add_argument("--out", type=Path, default=Path("results.csv"))
    args = ap.parse_args()

    prompts = load_prompts()
    qc = None
    if args.backtest:
        from ..src.qc_eval.qc_client import QCClient
        qc = QCClient()

    with open(args.generations) as f:
        gens = [json.loads(line) for line in f if line.strip()]

    rows = [score_one(g, prompts, qc) for g in gens]
    write_csv(rows, args.out)
    summarize(rows)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
