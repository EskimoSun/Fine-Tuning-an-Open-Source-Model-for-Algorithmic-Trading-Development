"""Draw a test-set-shaped sample from the training prompts.

    cd src && .venv/bin/python data/sample_train_prompts.py

The test set is 10 templates x 10 prompt versions, mostly equity strategies plus options and
futures. This draws 10 training templates with a fixed seed, stratified by asset class
(6 equity, 2 option, 1 future, 1 other), and keeps all 10 of each template's prompts, so the
sample has the same structure and a similar content mix. Alternative-data and live-trading
templates are left out. A group with too few templates is topped up from equity.
Writes data/train_prompts_sample100.jsonl with the rows unchanged, in the source file's order.
"""
import argparse
import collections
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "train_prompts.jsonl"
OUT = HERE / "train_prompts_sample100.jsonl"

EXCLUDE = ("alternative-data", "live-")       # live- covers live-trading-* and the other live-only templates
QUOTA = [("equity", 6), ("option", 2), ("future", 1), ("other", 1)]


def group_of(template_id):
    """Asset class from the folder name. No training folder is named option-*: the option templates
    are equity-options-*, index-options-* and intraday-*-options-*, so any name containing "option"
    counts as option unless it starts with future-."""
    if template_id.startswith("future-"):
        return "future"
    if "option" in template_id:
        return "option"
    if template_id.startswith("equity-"):
        return "equity"
    return "other"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(SOURCE))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    lines = [l for l in Path(args.source).read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [json.loads(l) for l in lines]
    by_template = collections.defaultdict(list)
    for row in rows:
        by_template[row["template_id"]].append(row)

    excluded = sorted(t for t in by_template if t.startswith(EXCLUDE))
    groups = collections.defaultdict(list)
    for template_id in sorted(by_template):      # sorted so the draw depends only on the seed
        if template_id not in excluded:
            groups[group_of(template_id)].append(template_id)

    rng = random.Random(args.seed)
    chosen, short = {}, 0
    for group, want in QUOTA:
        take = min(want, len(groups[group]))
        if take < want:
            print("group {} has {} template(s), {} needed: filling {} from equity".format(
                group, len(groups[group]), want, want - take))
            short += want - take
        for template_id in rng.sample(groups[group], take):
            chosen[template_id] = group
    if short:
        left = [t for t in groups["equity"] if t not in chosen]
        for template_id in rng.sample(left, short):
            chosen[template_id] = "equity (fill)"
    for template_id in chosen:
        versions = sorted(r["version"] for r in by_template[template_id])
        if versions != list(range(1, 11)):
            raise SystemExit("{} does not have versions 1-10: {}".format(template_id, versions))

    keep = set(chosen)
    kept = [line for line, row in zip(lines, rows) if row["template_id"] in keep]
    Path(args.out).write_text("\n".join(kept) + "\n", encoding="utf-8")

    print("{} templates in {}; {} excluded ({}*); available: {}".format(
        len(by_template), Path(args.source).name, len(excluded), "*, ".join(EXCLUDE),
        ", ".join("{} {}".format(g, len(groups[g])) for g, _n in QUOTA)))
    print("drew {} with seed {}:".format(len(chosen), args.seed))
    for template_id, group in chosen.items():
        print("  {:<14} {}".format(group, template_id))
    print("wrote {} prompts to {}".format(len(kept), args.out))


if __name__ == "__main__":
    main()
