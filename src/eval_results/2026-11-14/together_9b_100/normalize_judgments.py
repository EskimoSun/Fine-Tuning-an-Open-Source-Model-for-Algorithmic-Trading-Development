"""Recover one valid judge JSON object wrapped in Markdown and commentary.

Original responses are preserved. Scores and dimension evidence are never edited.
Conflicting judgments, schema errors, and transport failures remain unresolved.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = next(parent for parent in HERE.parents if (parent / "qc_eval/pipeline.py").exists())
sys.path.insert(0, str(SRC))
from qc_eval.fidelity import parse_judgment
from qc_eval.pipeline import save_record
from qc_eval.score import summarize

audit, unresolved = [], []
paths = sorted((HERE / "scoring/together_9b_tuned").glob("*.json"))
assert len(paths) == 100 and (HERE / "evaluation_complete.json").exists(), "Finish the full run first"
for path in paths:
    record = json.loads(path.read_text())
    original = record.get("fidelity", {})
    if original.get("status") == "judged":
        continue
    if original.get("status") != "invalid_judge_response":
        unresolved.append({"prompt_id": record["prompt_id"], "status": original.get("status")})
        continue
    text = original.get("raw_response", "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    try:
        obj, end = json.JSONDecoder().raw_decode(text)
        trailing = re.sub(r"^\s*```", "", text[end:]).strip()
        if re.search(r'"score"\s*:|\b(?:corrected|revised|correction)\b', trailing, re.I):
            raise ValueError("Trailing text may contain a conflicting judgment")
        parsed = parse_judgment(json.dumps(obj))
    except (ValueError, TypeError, KeyError) as exc:
        unresolved.append({"prompt_id": record["prompt_id"], "error": str(exc)})
        continue
    backup = HERE / "judge_original_responses" / path.name
    if not backup.exists():
        save_record(backup, record)
    normalization = {"method": "Extracted the first complete JSON object from Markdown; schema-validated without changing any judgment fields.",
                     "original_status": original["status"], "original_error": original.get("error"),
                     "extra_text": trailing, "original_record": str(backup.relative_to(HERE))}
    parsed.update(status="judged", raw_response=original["raw_response"], response_normalization=normalization)
    record["fidelity"] = parsed
    save_record(path, record)
    audit.append({"prompt_id": record["prompt_id"], "score": parsed["score"], **normalization})
results = [json.loads(path.read_text()) for path in paths]
save_record(HERE / "summary.json", summarize(results))
save_record(HERE / "judge_normalization.json", {"normalized": audit, "unresolved": unresolved})
print(json.dumps({"normalized": len(audit), "unresolved": unresolved, "summary": summarize(results)["all"]}, indent=2))
