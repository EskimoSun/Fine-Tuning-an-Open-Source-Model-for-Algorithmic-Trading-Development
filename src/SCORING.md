# Scoring existing Qwen generations

Run commands from the repository's `src` directory with the `.venv` activated.
Python 3.8 is supported. Existing dependencies (`requests`, `openpyxl`) suffice;
DTW is implemented with the Python standard library.

## Excel output

The agreed workbook is `QC_Eval_Prompt_Error_Sheet.xlsx`. Its original `Legend`,
`Results`, and `Summary` tabs and 100 prompt rows are retained. `Results` keeps
the original Fable / Qwen base / Qwen tuned / human columns. Repaired-code judge
scores belong on `QC Feedback`, not in the raw Qwen base column. `Judge Details`
contains eight requirement dimensions and candidate line evidence for each judgment.
All code and report output must use English.

The checked-in workbook includes the published random-ten baseline and three
feedback-repair candidates. It contains actual error counters, the original
Claude scores of 5/4/3, separate filled-order and closed-trade counts, timing error,
equity DTW, and review notes. Incompatible RSI date windows and failed futures
execution leave similarity cells blank. Gold executions do not fill the Fable
generation columns. Summary formulas have cached calculated values.

To refresh the workbook from the published snapshot without API calls, install
Node.js with `@oai/artifact-tool`, then run from `src`:

```bash
python -m qc_eval.export_excel --snapshot eval_results/2026-10-19
```

Use `--output` for a different destination and `--node` for an explicit Node.js
executable. If the package is installed outside the project, set
`ARTIFACT_TOOL_ROOT` to the directory containing that `node_modules` folder.
The exporter preserves the template layout and human-entered values, recalculates
formulas, and never generates candidates, submits backtests, or calls a judge.
Archived JSON judgments remain unchanged when report labels are translated.

## Use your QC account for automatic model repair

The pipeline, scoring command, and QC client now load the repository-root `.env`
automatically. Existing exported environment variables take precedence. Configure
`QC_USER_ID`, `QC_API_TOKEN`, `QWEN_BASE_URL`, `QWEN_API_KEY`, and `QWEN_BASE_MODEL`
there; no `source` command is needed. Credentials stay in the local API clients.

From `src`, run a bounded real QC feedback loop:

```bash
python -u -m qc_eval.pipeline --models qwen_base --prompt-id equity-bollinger-mean-reversion_v05 --repair-attempts 3 --skip-judge --verbose --print-output
```

This reuses the original real generation and source-matched QC execution when
available. For failed code it sends the prompt, current code, and selected QC
errors to the same model, then compiles/backtests the model's revised code on your
QC account. Each revised algorithm runs over the full requested period. It stops
on a completed backtest or after three model repairs; infrastructure failures are
reported rather than treated as algorithm errors. No mock or Gold template is
sent to the repair model. A small common API reference accompanies repair requests.

The baseline under `runs/qwen_base/` remains unchanged. Every model response,
repair request, Python file and QC result is stored under
`runs/qc_repair/qwen_base/<prompt_id>/`. Saved successful model responses are
reused on resume. Only completed candidates are published to
`runs/qwen_base_qc_repaired/`, with `model_qc_feedback_repair` provenance. Compare
these as a separate experiment. This mode writes JSON records rather than the
legacy Excel workbook; `--regenerate`, `--rerun-qc`, and judge flags do not alter
the repair-mode cache or invoke a judge. Use `qc_eval.score` separately:

```bash
python -m qc_eval.score --models qwen_base_qc_repaired --prompt-id equity-bollinger-mean-reversion_v05 --qc --require-real --verbose
```

Successful execution is not a 1–5 prompt adherence judgment. Add `--judge` only
after configuring the judge. Failed/unavailable metrics remain unscored.

Real smoke test: Bollinger `v05` reused its original `self.Indicator` failure,
then completed on the first Qwen repair with 4 orders and 2 closed trades.
QC project `38140214`, backtest `08119b5d0529beeedc2fc5c9d0e9dd08`.

## Recommended interpretation

Report three separate results:

1. **Prompt fidelity (1–5):** the existing rubric, judged from the prompt and
   candidate code, with requirement-level evidence and candidate line numbers.
2. **Execution:** successful completion, syntax/compile error, runtime error,
   timeout, or infrastructure failure. Running successfully is not proof of
   prompt adherence, and an execution failure does not automatically set fidelity.
3. **Template similarity:** deterministic comparisons of actual executions.
   A close match supports fidelity but does not establish it.

Do not average DTW, trade counts, and an LLM score into a single 1–5 score.
There is no calibrated conversion between those metrics and this rubric.
For example, a vague RSI request may allow RSI(10) or RSI(14); the template's
RSI(14) is not an extra requirement. The prompt takes priority when the template
and prompt disagree. Such conflicts are flagged for human review.

For precise and ceiling prompts, investigate large behavioral discrepancies.
For vague prompts, use behavior to find suspicious cases, not to penalize
reasonable unspecified choices. Validate a sample of requirement-level judgments
with a human before comparing models. Predeclare tolerances per strategy family
after observing repeatability of the gold backtests, not after viewing Qwen scores.
Keep QC engine/data/brokerage/fill/fee settings consistent where the prompt allows;
record environment differences when interpreting comparisons.

## 1. Generate real candidate code, if needed

The scoring command never generates or changes Qwen outputs. It reads:

```text
src/runs/qwen_base/<prompt_id>.json
```

Your earlier `--mock` run saved fake code. Replace that with real generations:

```bash
export QWEN_BASE_URL="your_openai_compatible_provider_base_url"
export QWEN_API_KEY="your_provider_key"
export QWEN_BASE_MODEL="a_valid_model_id_on_that_endpoint"

python -m qc_eval.pipeline --models qwen_base --limit 5 --no-qc --skip-judge
```

`--skip-judge` avoids paying for the old, shorter judge before running the new
requirement-level judge. `--no-qc` leaves execution to the scoring command.
Real runs automatically replace cached mock generations and preserve existing
real outputs, including failed baseline attempts. Do not use `--regenerate` when
continuing a baseline: it replaces real outputs too. Reserve it for a separately
tracked experiment.
The old pipeline's Excel workbook is separate from the new JSON reports.

## 2. Score existing code

```bash
export QC_USER_ID="your_user_id"
export QC_API_TOKEN="your_qc_token"
export ANTHROPIC_API_KEY="your_anthropic_key"
export FABLE_MODEL="a_valid_anthropic_model_id"

python -m qc_eval.score --models qwen_base --limit 5 --qc --judge
```

`--qc` authenticates, reuses source-matched cached backtests when possible,
creates cloud projects/backtests for missing evaluations, and downloads orders
and equity charts. It uses the actual files under `data/templates/` as gold.
Gold executions are cached once per template/source hash. This flag uses your QC
cloud resources. Projects created by evaluation remain in your account.

`--judge` makes paid Anthropic calls and requires an explicit `FABLE_MODEL`.
The same model grades every candidate using the shared rubric in `qc_eval/rubric.py`.
The Anthropic client omits sampling parameters for modern model compatibility,
extracts only text blocks, and rejects token-truncated replies. The detailed judge
uses an 8192-token output budget, shared by thinking and answer text on Opus 5.5.
It sees the template as an example, with explicit instructions that the prompt
is authoritative. It checks assets, indicators, parameters, entries, exits,
dates, resolution/schedule, and sizing. Missing, malformed, or contradictory judge
responses get a null score and a human-review flag, not a fabricated grade.
Judging the prompt does not require a successful gold or candidate backtest.

No flags means offline: reuse collected evidence and prior source/prompt/model-
matched judgments, calculate diagnostics, and save judge requests for inspection.
Missing evidence stays unavailable:

```bash
python -m qc_eval.score --models qwen_base --limit 5
```

Other examples:

```bash
# All 100 prompts, base and tuned outputs already generated:
python -m qc_eval.score --models qwen_base,qwen_tuned --qc --judge

# One prompt, and a strict timestamp match with no DTW time shifting:
python -m qc_eval.score --prompt-id equity-rsi-overbought-oversold_v02 --time-tolerance-seconds 0 --dtw-window 0 --qc --judge

# Explicitly replace old execution evidence or judge results:
python -m qc_eval.score --limit 5 --qc --rerun-qc --judge --rejudge
```

You can also supply a JSONL of existing generations with `--generations FILE`.
Each line must contain `prompt_id`, `model` (matching `--models`), and `output`
(raw model text or raw algorithm Python). `model_id` and `qc_evaluation` are
optional. Prompt IDs must match `data/prompts_100.jsonl`. Duplicate (model,
prompt_id) pairs are rejected. Existing pipeline caches are not modified.

## Print real outputs and execution evidence

To print the actual provider response (including its model ID and whether it was
newly generated or loaded from cache), use:

```bash
python -u -m qc_eval.pipeline --models qwen_base --limit 5 --no-qc --skip-judge --print-output
```

Missing outputs and old mock entries are replaced with real provider responses.
Existing real outputs, even invalid strategies, are retained. Short HTTP 429/503
failures are retried at most twice; unsuccessful requests never return fake code.
Use repeatable `--prompt-id` arguments to select individual prompts.

For a reviewed repair with visible cloud progress, source code, statistics,
compile diagnostics, log tail and behavior metrics:

```bash
python -u -m qc_eval.score --models qwen_repaired --prompt-id equity-rsi-overbought-oversold_v02 --qc --print-output --verbose --require-real
```

`--require-real` rejects missing/mock entries before any QC authentication or
job submission. `--verbose` labels reused backtests explicitly and shows cloud
stages/progress for new ones. A reused result remains evidence from an actual
cloud job; `--rerun-qc` requests new cloud executions if needed. `--print-output`
prints saved candidate text; repaired text is labeled `manual_code_repair`.

Cloud equity supports named point objects as well as compact arrays; candle
arrays use their close, following LEAN's
[candlestick serializer](https://www.lean.io/docs/v2/lean-engine/class-reference/CandlestickJsonConverter_8cs_source.html).

## Behavior measurements

| Measurement | Meaning | Best match |
|---|---|---|
| Closed-trade count | QC `totalPerformance.tradeStatistics.totalNumberOfTrades`, when supplied | Same count |
| Filled-order count | Orders with executions; submitted/rejected/unfilled orders are separate | Relative error 0 |
| Fill-event count | Individual fills, including partial fills and option/futures legs | Same count |
| Fill matching | One-to-one matches on security ID, buy/sell direction, and UTC time within tolerance | Precision/recall/F1 1 |
| Quantity error | Mean relative quantity error among matched fills only | 0 |
| Timing error | Mean absolute timestamp difference among matched fills only | 0 seconds |
| Trading interval | Gaps between distinct execution timestamps; simultaneous legs count once | Quantile MAE 0 seconds |
| Position direction | Time-weighted per-security long/flat/short agreement inferred from fills | 1 |
| Equity MAE | Same-date error in cumulative return from first shared equity observation | 0 |
| Equity DTW | Path-normalized absolute-cost DTW on cumulative-return curves | 0 |

Default fill tolerance is 60 seconds. Set `--time-tolerance-seconds` yourself;
this is a diagnostic parameter, not a universal correctness threshold. Quantities
do not affect fill-match F1, so also inspect the quantity error. Matching partial
fills one-to-one makes fill segmentation differences visible. Positions are
reconstructed from fills, so splits or other non-order holding adjustments can
make this proxy inaccurate. Both-flat intervals are excluded from direction
agreement; an algorithm that does nothing cannot get a perfect trade score.

The chart API requests up to 10,000 observations. Equity is resampled to the last
available value per UTC day and normalized by initial equity, not by standard
deviation. Comparisons require matching first/last observed dates and at least
95% common daily coverage. No interpolation or future filling is performed.
DTW defaults to a one-observation Sakoe–Chiba band. This limits alignment to
adjacent available daily observations, not necessarily one calendar day. DTW
distance is in return units (0.01 means one percentage point average path error).
Always read same-date MAE and fill timing alongside DTW: warping can hide delay.
Daily equity cannot prove an intraday rule was followed. There is no universal
DTW pass threshold; calibrate on gold repeat runs and controlled rule mutations.

Actual order-event timestamps/quantities are used when available. A fully filled
order without events falls back to `lastFillTime` and is explicitly counted as
approximated. Partially filled orders without fill-event evidence are unscorable.
Missing order pages, missing charts, failed runs, no trade opportunities, or bad
reference templates are not silently scored as successful matches.

QC API references: [orders](https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/backtest-management/read-backtest/orders),
[charts](https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/backtest-management/read-backtest/charts),
[backtest statistics](https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/backtest-management/read-backtest/backtest-statistics).

## Outputs and reproducibility

```text
src/runs/scoring/
  summary.json
  qwen_base/<prompt_id>.json
  evaluations/gold/<template_id>.json
  evaluations/qwen_base/<prompt_id>.json
```

Each prompt report stores its prompt, source hashes, reference path, judge model,
full judge request/response, per-dimension evidence, execution status, and raw
behavior metrics. Summary counts all requested rows, reports scored denominators,
judge statuses, and fidelity distributions; null scores are never treated as zero.
Source hashes invalidate stale execution evidence; changed prompt/reference/code/
judge input invalidates the corresponding cached fidelity judgment. The files
under `evaluations/` retain raw API evidence. Transient execution failures remain
cached until `--rerun-qc`; evidence-fetch failures are retried with `--qc`.

Run offline tests from `src`:

```bash
python -m unittest discover -s ../tests -v
```
