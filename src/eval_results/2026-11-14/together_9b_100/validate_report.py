"""Read-only reconciliation of 100-prompt evidence and the exported workbook."""
import ast
import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path

from openpyxl import load_workbook

HERE = Path(__file__).resolve().parent
SRC = next(parent for parent in HERE.parents if (parent / "qc_eval/pipeline.py").exists())
sys.path.insert(0, str(SRC))
from qc_eval.config import load_env
from qc_eval.static_checks import extract_code

OUTPUT = SRC / "outputs/01a155af-3583-7582-b58f-357580fa892d/Together_9B_Full_100_Evaluation.xlsx"
if (HERE / OUTPUT.name).exists():
    OUTPUT = HERE / OUTPUT.name
data = json.loads((HERE / "workbook_data.json").read_text())
rows = data["rows"]
assert len(rows) == 100 and len({r["prompt_id"] for r in rows}) == 100
assert all(r["model_id"] == "jared-309b/Qwen-9B-finetune" for r in rows)
workbook = load_workbook(OUTPUT, data_only=True)
formulas = load_workbook(OUTPUT, data_only=False)
assert workbook.sheetnames == ["Legend", "Results", "Summary", "QC Feedback", "Judge Details"]
sheet = workbook["Results"]
for n, row in enumerate(rows, 3):
    assert [sheet.cell(n, c).value for c in range(12, 15)] == [row["compile_errors"], row["runtime_errors"], row["fidelity"]]
    assert sheet.cell(n, 5).value == data["prompts"][n - 3]["prompt"]
assert all(sheet.cell(r, c).value is None for r in range(3, 103) for c in range(6, 12))
assert all(sheet.cell(r, c).value is None for r in range(3, 103) for c in (15, 16))
assert sum(sheet.cell(r, 5).value is not None for r in range(3, 103)) == 100
assert formulas["Results"].freeze_panes == "F3"
assert len(formulas["Results"].data_validations.dataValidation) == 2
assert "Qwen tuned" in sheet["P2"].value
summary = workbook["Summary"]
assert summary["B13"].value == 0
scores = [r["fidelity"] for r in rows if r["fidelity"] is not None]
expected = [100, sum(r["qc_status"] == "completed" for r in rows), len(scores), sum(scores) / len(scores),
            sum(r["needs_human_review"] for r in rows),
            sum(r["behavior_status"] == "available" for r in rows), sum(r["behavior_status"] == "partial" for r in rows)]
for n, value in enumerate(expected, 47):
    actual = summary[f"B{n}"].value
    assert abs(actual - value) < 1e-10, (n, actual, value)
pending = sum(r["qc_status"] not in {"completed", "runtime_error", "syntax_error", "compile_error"} for r in rows)
assert summary["B54"].value == pending
if pending:
    assert summary["D9"].value == "-"
else:
    assert abs(summary["D9"].value - expected[1] / 100) < 1e-10
assert abs(summary["D10"].value - expected[3]) < 1e-10
assert all(summary[f"E{r}"].value == "-" for r in range(4, 11))
assert sum(workbook["Judge Details"].cell(r, 1).value is not None for r in range(4, 4 + len(data["dimension_rows"]))) == len(data["dimension_rows"])
for index, metrics in enumerate(data["behavior_rows"], 110):
    assert [workbook["QC Feedback"].cell(index, c).value for c in range(1, 12)] == metrics
    if rows[index - 110]["qc_status"] != "completed":
        assert all(metrics[c] is None for c in (1, 3, 5, 6, 7, 8)), "Failed candidate has behavioral measurements"
errors = {"#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!", "#SPILL!", "#CALC!"}
for ws in workbook:
    for cells in ws:
        for cell in cells:
            if isinstance(cell.value, str):
                assert cell.value not in errors, (ws.title, cell.coordinate)
                assert not re.search(r"[\u3400-\u9fff]", cell.value), (ws.title, cell.coordinate)
checksums = []
for row in rows:
    pid = row["prompt_id"]
    record = json.loads((HERE / "generations/qwen_tuned" / (pid + ".json")).read_text())
    source = (HERE / "candidates" / (pid + ".py")).read_text()
    assert source == extract_code(record["output"])
    assert hashlib.sha256(source.encode()).hexdigest() == row["source_sha256"]
    english = (HERE / "candidates_english" / (pid + ".py")).read_text()
    assert english == source.replace("buy\u655e\u53e3", "buy exposure")
    assert not re.search(r"[\u3400-\u9fff]", english)
    try:
        assert ast.dump(ast.parse(english)) == ast.dump(ast.parse(source))
    except SyntaxError:
        assert row["qc_status"] in {"syntax_error", "deferred", "infrastructure_error"}
    checksums.append({"prompt_id": pid, "source_sha256": row["source_sha256"],
                      "output_sha256": hashlib.sha256(record["output"].encode()).hexdigest()})
load_env()
secrets = [v for k, v in os.environ.items() if len(v) >= 12 and ("API_KEY" in k or "TOKEN" in k)]
checked = 0
for root in dict.fromkeys((HERE, OUTPUT.parent)):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        chunks = []
        if path.suffix == ".xlsx":
            with zipfile.ZipFile(path) as archive:
                chunks = [archive.read(n).decode("utf-8", errors="replace") for n in archive.namelist() if n.endswith(".xml")]
        elif path.suffix in (".py", ".mjs", ".json", ".jsonl", ".md", ".log", ".txt", ".csv", ".ndjson"):
            chunks = [path.read_text(errors="replace")]
        if chunks:
            checked += 1
            assert all(secret not in chunk for secret in secrets for chunk in chunks), "Credential found in artifact"
report = {"status": "passed", "prompt_rows": 100, "source_hashes_verified": len(checksums),
          "judge_dimensions": len(data["dimension_rows"]), "formula_errors": 0,
          "credential_files_checked": checked, "workbook_language": "English",
          "workbook_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
          "workbook_data_sha256": hashlib.sha256((HERE / "workbook_data.json").read_bytes()).hexdigest()}
(HERE / "source_checksums.json").write_text(json.dumps(checksums, indent=2) + "\n")
(HERE / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
