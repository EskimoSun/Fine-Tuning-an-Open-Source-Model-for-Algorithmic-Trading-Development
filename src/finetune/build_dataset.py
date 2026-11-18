"""
Build the supervised fine-tuning set (chat JSONL) from sources that never touch the test set.

    python -m finetune.build_dataset                 # all sources, report leakage
    python -m finetune.build_dataset --require-qc    # keep only templates that passed QC (see validate_qc)

Sources
  1. data/train_templates/<folder>/main.py   QuantConnect's own project templates (Apache 2.0),
     minus the 10 used for evaluation. Their code is the target answer.
  2. data/train_prompts_src.txt              hand-written requests for those templates
     (individual/startup/institutional style), plus each template's own description and spec.
  3. data/qc_faq_writing_algorithms.md       QuantConnect's Writing Algorithms FAQ (question -> answer).

Leakage guard: eval templates are excluded by folder, and every prompt and code target is
compared with data/prompts_100.jsonl and data/templates/*/main.py. Anything too similar is dropped.

Output (finetune/out/): train.jsonl, val.jsonl (whole templates held out), manifest.json.
"""

import argparse
import difflib
import hashlib
import json
import re
from pathlib import Path

from qc_eval.pipeline import SYSTEM

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TRAIN_TEMPLATES = DATA / "train_templates"
EVAL_TEMPLATES = DATA / "templates"
PROMPTS_SRC = DATA / "train_prompts_src.txt"
FAQ = DATA / "qc_faq_writing_algorithms.md"
EVAL_PROMPTS = DATA / "prompts_100.jsonl"
QC_VALIDATION = Path(__file__).resolve().parent / "qc_validation.json"
OUT = Path(__file__).resolve().parent / "out"

# FAQ answers are prose, so they must not sit under the "return one main.py" system prompt.
FAQ_SYSTEM = ("You answer questions about writing QuantConnect LEAN algorithms in Python "
              "using the current snake_case API. Answer in English, briefly and accurately.")

PROMPT_SIM_MAX = 0.6   # token Jaccard vs any eval prompt
CODE_SIM_MAX = 0.8     # difflib ratio vs any eval gold template


def tokens(text):
    return set(re.findall(r"[a-z0-9_.]+", text.lower()))


def jaccard(a, b):
    return len(a & b) / max(1, len(a | b))


def code_lines(code):
    """Non-empty, non-comment lines with whitespace removed: line-level similarity."""
    out = []
    for line in code.splitlines():
        line = re.sub(r"\s+", "", line)
        if line and not line.startswith("#") and not line.startswith("```"):
            out.append(line)
    return out


def eval_folders():
    return {p.name for p in EVAL_TEMPLATES.iterdir() if p.is_dir()}


def load_template_codes():
    excluded = eval_folders()
    codes = {}
    for d in sorted(TRAIN_TEMPLATES.iterdir()):
        main = d / "main.py"
        if d.is_dir() and main.exists() and d.name not in excluded:
            codes[d.name] = main.read_text(encoding="utf-8").strip()
    return codes


def load_meta():
    path = TRAIN_TEMPLATES / "templates_meta.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def load_prompt_rows():
    rows = []
    for n, line in enumerate(PROMPTS_SRC.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(" | ", 3)]
        if len(parts) != 4:
            raise ValueError("bad line {} in {}".format(n, PROMPTS_SRC.name))
        folder, segment, specificity, prompt = parts
        rows.append({"template_id": folder, "segment": segment,
                     "specificity": specificity, "prompt": prompt, "source": "handwritten"})
    return rows


def template_examples(codes, meta):
    rows = [r for r in load_prompt_rows() if r["template_id"] in codes]
    unknown = {r["template_id"] for r in load_prompt_rows()} - set(codes)
    for folder in codes:
        m = meta.get(folder) or {}
        if m.get("description"):
            rows.append({"template_id": folder, "segment": "reference", "specificity": "description",
                         "prompt": m["description"], "source": "qc_templates_json"})
        if m.get("spec"):
            rows.append({"template_id": folder, "segment": "reference", "specificity": "spec",
                         "prompt": m["spec"], "source": "qc_templates_json"})
    for r in rows:
        r["kind"] = "template"
        r["answer"] = "```python\n{}\n```".format(codes[r["template_id"]])
    return rows, sorted(unknown)


PASCAL_ALIAS = re.compile(r" \(`[A-Z][A-Za-z0-9]*`\)")


def faq_examples():
    """### Question / answer paragraphs. Drops the Docs: link and PascalCase aliases."""
    rows, section = [], None
    text = FAQ.read_text(encoding="utf-8")
    for block in re.split(r"\n(?=#{2,3} )", text):
        head, _, body = block.partition("\n")
        if head.startswith("## "):
            section = head[3:].strip()
            continue
        if not head.startswith("### "):
            continue
        body = re.sub(r"\n?Docs: <[^>]+>\s*$", "", body.strip()).strip()
        body = PASCAL_ALIAS.sub("", body)
        if len(body) < 40:
            continue
        rows.append({"kind": "faq", "template_id": None, "segment": "faq", "specificity": section,
                     "source": "qc_faq", "prompt": head[4:].strip(), "answer": body})
    return rows


def leakage(rows):
    eval_prompts = [tokens(json.loads(l)["prompt"]) for l in EVAL_PROMPTS.read_text().splitlines() if l.strip()]
    gold = {p.parent.name: code_lines(p.read_text(encoding="utf-8")) for p in EVAL_TEMPLATES.glob("*/main.py")}
    code_sim = {}
    kept, dropped = [], []
    for r in rows:
        p_sim = max(jaccard(tokens(r["prompt"]), e) for e in eval_prompts)
        c_sim = 0.0
        if r["kind"] == "template":
            folder = r["template_id"]
            if folder not in code_sim:
                code_sim[folder] = max(difflib.SequenceMatcher(None, code_lines(r["answer"]), g).ratio()
                                       for g in gold.values())
            c_sim = code_sim[folder]
        r["max_prompt_sim"], r["max_code_sim"] = round(p_sim, 3), round(c_sim, 3)
        (dropped if p_sim > PROMPT_SIM_MAX or c_sim > CODE_SIM_MAX else kept).append(r)
    return kept, dropped


def qc_passed():
    if not QC_VALIDATION.exists():
        return None
    results = json.loads(QC_VALIDATION.read_text())
    return {k for k, v in results.items() if v.get("status") == "completed"}


def is_val(template_id, frac):
    if template_id is None:
        return False
    h = int(hashlib.sha256(template_id.encode()).hexdigest(), 16)
    return (h % 1000) / 1000 < frac


def to_chat(r):
    system = FAQ_SYSTEM if r["kind"] == "faq" else SYSTEM
    return {"messages": [{"role": "system", "content": system},
                         {"role": "user", "content": r["prompt"]},
                         {"role": "assistant", "content": r["answer"]}]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--require-qc", action="store_true",
                    help="drop templates without a completed backtest in finetune/qc_validation.json")
    ap.add_argument("--no-faq", action="store_true")
    ap.add_argument("--val-frac", type=float, default=0.1, help="share of templates held out for validation")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)

    codes = load_template_codes()
    rows, unknown = template_examples(codes, load_meta())
    if unknown:
        raise SystemExit("prompts reference missing or eval templates: {}".format(unknown))
    if not args.no_faq:
        rows += faq_examples()

    rows, dropped = leakage(rows)
    passed = qc_passed()
    skipped_qc = []
    if args.require_qc:
        if passed is None:
            raise SystemExit("--require-qc needs finetune/qc_validation.json; run finetune.validate_qc first")
        skipped_qc = sorted({r["template_id"] for r in rows if r["kind"] == "template" and r["template_id"] not in passed})
        rows = [r for r in rows if r["kind"] != "template" or r["template_id"] in passed]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    train = [r for r in rows if not is_val(r["template_id"], args.val_frac)]
    val = [r for r in rows if is_val(r["template_id"], args.val_frac)]
    for name, part in (("train", train), ("val", val)):
        with open(out / "{}.jsonl".format(name), "w", encoding="utf-8") as f:
            for r in part:
                f.write(json.dumps(to_chat(r), ensure_ascii=False) + "\n")

    def count(part, key):
        c = {}
        for r in part:
            c[r[key]] = c.get(r[key], 0) + 1
        return c

    manifest = {
        "system_prompt": "qc_eval.pipeline.SYSTEM (v1) for code; FAQ_SYSTEM for FAQ answers",
        "train_examples": len(train), "val_examples": len(val),
        "train_by_kind": count(train, "kind"), "train_by_source": count(train, "source"),
        "templates_used": len({r["template_id"] for r in rows if r["template_id"]}),
        "val_templates": sorted({r["template_id"] for r in val}),
        "excluded_eval_templates": sorted(eval_folders()),
        "dropped_for_similarity": [{k: r[k] for k in ("template_id", "prompt", "max_prompt_sim", "max_code_sim")}
                                   for r in dropped],
        "skipped_not_qc_passed": skipped_qc,
        "qc_validation_present": passed is not None,
        "max_prompt_sim_kept": max((r["max_prompt_sim"] for r in rows), default=0),
        "max_code_sim_kept": max((r["max_code_sim"] for r in rows), default=0),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print(json.dumps({k: manifest[k] for k in ("train_examples", "val_examples", "train_by_source",
                                                "templates_used", "max_prompt_sim_kept", "max_code_sim_kept")}, indent=1))
    print("dropped for similarity:", len(dropped), "| not QC-passed:", len(skipped_qc))
    return manifest


if __name__ == "__main__":
    main()
