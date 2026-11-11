"""
Validates the training golden set written by build_train_prompts.py.

    python validate_train_prompts.py            # from src/data
    python validate_train_prompts.py --strict   # non-zero exit on any failure

Checks
  format      every row of train_prompts_src.txt is `folder | segment | specificity | prompt`,
              the folder exists in data/train_templates and is not a test template,
              segment/specificity are grid labels, no empty prompts
  coverage    10 rows per in-scope template, exactly one per grid cell
  unique      no two prompts identical (case/whitespace-insensitive)
  parameters  every non-vague prompt states the template's start date, end date and cash
              where the template code sets them
  leakage     token Jaccard vs the 100 test prompts <= 0.6 (the same guard as
              finetune/build_dataset.py), reported with the maximum
  jsonl       train_prompts.jsonl matches the txt rows
Prints counts per template and per grid cell.
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
TXT = HERE / "train_prompts_src.txt"
JSONL = HERE / "train_prompts.jsonl"
TRAIN = HERE / "train_templates"
TEST = HERE / "templates"
TEST_PROMPTS = HERE / "prompts_100.jsonl"
EXCLUDED = {"alternative-data", "alternative-data-chain-universe-eodhdupcomingdividends"}

GRID = [
    ("individual", "vague"), ("individual", "precise"), ("individual", "over_specified"),
    ("startup", "vague"), ("startup", "precise"), ("startup", "over_specified"),
    ("institutional", "vague"), ("institutional", "precise"), ("institutional", "over_specified"),
    ("reference", "ceiling"),
]
PROMPT_SIM_MAX = 0.6

MONTHS = {1: ["jan", "january"], 2: ["feb", "february"], 3: ["mar", "march"], 4: ["apr", "april"],
          5: ["may"], 6: ["jun", "june"], 7: ["jul", "july"], 8: ["aug", "august"],
          9: ["sep", "sept", "september"], 10: ["oct", "october"], 11: ["nov", "november"],
          12: ["dec", "december"]}


def date_patterns(y, m, d):
    pats = [rf"\b{y}-{m:02d}-{d:02d}\b", rf"\b{y}-{m}-{d}\b", rf"\b{y},\s*{m},\s*{d}\b",
            rf"\b{m}/{d}/{y}\b", rf"\b{m:02d}/{d:02d}/{y}\b", rf"\b{y}/{m:02d}/{d:02d}\b"]
    suffix = r"(?:st|nd|rd|th)?"
    for name in MONTHS[m]:
        pats.append(rf"\b{name}\.?\s+{d}{suffix},?\s+{y}\b")
        pats.append(rf"\b{d}{suffix}\s+(?:of\s+)?{name}\.?,?\s+{y}\b")
        pats.append(rf"\b{name}\.?\s+{d}{suffix}\b")   # month + day, year given elsewhere
        pats.append(rf"\b{d}{suffix}\s+(?:of\s+)?{name}\b")
    return pats


def mentions_date(text, ymd):
    y, m, d = ymd
    t = text.lower()
    if not re.search(rf"\b{y}\b", t):
        return False
    return any(re.search(p, t) for p in date_patterns(y, m, d))


def cash_patterns(c):
    pats = [rf"\b{c}\b", rf"\b{c:,}\b"]
    s = str(c)
    if c % 1000 == 0:
        k = c // 1000
        pats += [rf"\b{k}k\b", rf"\${k}k\b", rf"\b{k},000\b", rf"\b{k}_000\b", rf"\b{k} thousand\b"]
        if k % 1000 == 0:
            mm = k // 1000
            pats += [rf"\b{mm}m\b", rf"\${mm}m\b", rf"\b{mm} million\b", rf"\b{mm}mm\b", rf"\b{mm}_000_000\b"]
    return pats


def mentions_cash(text, c):
    t = text.lower().replace("usd ", "")
    return any(re.search(p, t) for p in cash_patterns(c))


def code_params(folder):
    code = (TRAIN / folder / "main.py").read_text(encoding="utf-8")
    s = re.search(r"set_start_date\((\d+),\s*(\d+),\s*(\d+)\)", code)
    e = re.search(r"set_end_date\((\d+),\s*(\d+),\s*(\d+)\)", code)
    c = re.search(r"set_cash\(([\d_,]+)\)", code)
    return (tuple(int(x) for x in s.groups()) if s else None,
            tuple(int(x) for x in e.groups()) if e else None,
            int(c.group(1).replace("_", "").replace(",", "")) if c else None)


def tokens(text):
    return set(re.findall(r"[a-z0-9_.]+", text.lower()))


def jaccard(a, b):
    return len(a & b) / max(1, len(a | b))


def norm(text):
    return re.sub(r"\s+", " ", text.strip().lower())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)
    failures = []

    train_folders = {p.name for p in TRAIN.iterdir() if p.is_dir()}
    test_folders = {p.name for p in TEST.iterdir() if p.is_dir()}
    in_scope = sorted(train_folders - EXCLUDED)

    rows = []
    for n, line in enumerate(TXT.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(" | ", 3)]
        if len(parts) != 4 or not all(parts):
            failures.append(f"format: line {n} does not split into 4 non-empty fields")
            continue
        folder, segment, spec, prompt = parts
        if folder in test_folders:
            failures.append(f"format: line {n} uses TEST template {folder}")
        elif folder not in train_folders:
            failures.append(f"format: line {n} unknown folder {folder}")
        if (segment, spec) not in GRID:
            failures.append(f"format: line {n} cell ({segment}, {spec}) not in grid")
        rows.append({"line": n, "folder": folder, "segment": segment, "spec": spec, "prompt": prompt})

    # coverage
    by_folder = defaultdict(list)
    for r in rows:
        by_folder[r["folder"]].append(r)
    complete = []
    for folder in in_scope:
        cells = Counter((r["segment"], r["spec"]) for r in by_folder.get(folder, []))
        if sum(cells.values()) == 0:
            continue  # not written yet
        dup = [c for c, v in cells.items() if v > 1]
        missing = [c for c in GRID if c not in cells]
        if dup:
            failures.append(f"coverage: {folder} has duplicate cells {dup}")
        if missing:
            failures.append(f"coverage: {folder} missing cells {missing}")
        if not dup and not missing:
            complete.append(folder)

    # uniqueness
    seen = {}
    for r in rows:
        key = norm(r["prompt"])
        if key in seen:
            failures.append(f"unique: line {r['line']} duplicates line {seen[key]}")
        else:
            seen[key] = r["line"]

    # parameters
    for r in rows:
        if r["spec"] == "vague" or r["folder"] not in train_folders:
            continue
        start, end, cash = code_params(r["folder"])
        miss = []
        if start and not mentions_date(r["prompt"], start):
            miss.append(f"start {start}")
        if end and not mentions_date(r["prompt"], end):
            miss.append(f"end {end}")
        if cash and not mentions_cash(r["prompt"], cash):
            miss.append(f"cash {cash}")
        if miss:
            failures.append(f"parameters: line {r['line']} {r['folder']} {r['segment']}/{r['spec']} missing {miss}")

    # leakage
    test_tok = [tokens(json.loads(l)["prompt"]) for l in TEST_PROMPTS.read_text(encoding="utf-8").splitlines() if l.strip()]
    max_sim, max_row = 0.0, None
    for r in rows:
        sim = max(jaccard(tokens(r["prompt"]), t) for t in test_tok)
        if sim > max_sim:
            max_sim, max_row = sim, r
        if sim > PROMPT_SIM_MAX:
            failures.append(f"leakage: line {r['line']} {r['folder']} Jaccard {sim:.2f} vs a test prompt")

    # jsonl
    if JSONL.exists():
        jrows = [json.loads(l) for l in JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
        jset = {(j["template_id"], j["segment"], j["specificity"], j["prompt"]) for j in jrows}
        tset = {(r["folder"], r["segment"], r["spec"], r["prompt"]) for r in rows if r["folder"] in complete}
        if jset != tset:
            failures.append(f"jsonl: {len(jset - tset)} rows only in jsonl, {len(tset - jset)} only in txt")
    else:
        failures.append("jsonl: train_prompts.jsonl missing")

    # report
    print(f"rows: {len(rows)}   templates with rows: {len(by_folder)}   complete (10/10): {len(complete)} of {len(in_scope)} in scope")
    print("per grid cell:")
    cell_counts = Counter((r["segment"], r["spec"]) for r in rows)
    for c in GRID:
        print(f"  {c[0]:>13} / {c[1]:<14} {cell_counts.get(c, 0)}")
    print("per template:")
    for folder in in_scope:
        n = len(by_folder.get(folder, []))
        print(f"  {n:>2}  {folder}")
    not_started = [f for f in in_scope if f not in by_folder]
    print(f"not started: {len(not_started)}")
    print(f"max prompt Jaccard vs test set: {max_sim:.3f}" + (f"  (line {max_row['line']} {max_row['folder']})" if max_row else ""))
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  " + f)
    if args.strict and failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
