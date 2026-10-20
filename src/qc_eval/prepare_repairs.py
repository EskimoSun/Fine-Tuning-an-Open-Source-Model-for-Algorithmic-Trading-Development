"""Package reviewed strategy repairs as separate, provenance-linked generations.

    python -m qc_eval.prepare_repairs
    python -m qc_eval.score --models qwen_repaired --limit 5 --qc

Does not change or resample original Qwen outputs. Never calls a model or QC.
"""

import argparse
import ast
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .pipeline import ROOT, RUNS, save_record
from .static_checks import extract_code


def _sha(code):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def prepare(manifest_path, runs=RUNS):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source, target = manifest["source_model"], manifest["target_model"]
    labels = [source, target] + [r["prompt_id"] for r in manifest["repairs"]]
    if source == target or any(Path(x).name != x or x in (".", "..") for x in labels):
        raise ValueError("Repair labels must be simple names; source and target must differ")
    pending = []
    for repair in manifest["repairs"]:
        pid = repair["prompt_id"]
        original_path = runs / source / (pid + ".json")
        original = json.loads(original_path.read_text(encoding="utf-8"))
        if original.get("model_id") == "mock":
            raise ValueError("Cannot repair a mock output: " + pid)
        original_code = extract_code(original["output"])
        if original_code is None or _sha(original_code) != repair["source_sha256"]:
            raise ValueError("Source changed; review the repair again before applying: " + pid)
        code_path = (manifest_path.parent / repair["file"]).resolve()
        if manifest_path.parent.resolve() not in code_path.parents:
            raise ValueError("Repair file is outside the manifest directory")
        code = code_path.read_text(encoding="utf-8")
        ast.parse(code, filename=str(code_path))
        record = {"prompt_id": pid, "model": target, "model_id": original.get("model_id"),
                  "output": "```python\n" + code + "\n```", "has_code": True,
                  "generated_at": original.get("generated_at"),
                  "intervention": manifest["intervention"],
                  "repair": {"source_model": source, "source_sha256": repair["source_sha256"],
                             "repaired_sha256": _sha(code), "changes": repair["changes"],
                             "prepared_at": datetime.now(timezone.utc).isoformat()}}
        pending.append((runs / target / (pid + ".json"), record))
    # Validate every source/file before writing any repaired generation.
    for path, record in pending:
        save_record(path, record)
    return [path for path, _ in pending]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "repairs/qwen_base/manifest.json")
    args = parser.parse_args()
    for path in prepare(args.manifest):
        print("Prepared repaired generation: " + str(path))
    print("Original qwen_base generations and evaluations were preserved.")


if __name__ == "__main__":
    main()
