# Prompt-engineering condition: system prompt v2 (random 10)

Same 10 prompts as the original baseline (seed 42, see
[baseline manifest](../../2026-10-19/baseline_random10/manifest.json)), same model
(`qwen/qwen3.8-27b` via Groq, temperature 0), same QC compile + backtest. The only
change is the system prompt: `SYSTEM_V2` in `src/qc_eval/pipeline.py`, which
extends the original `SYSTEM` with LEAN snake_case API rules. It contains no test
prompts and no gold template code. The original baseline is unchanged.

```bash
cd src
python -u -m qc_eval.pipeline --models qwen_base --system v2 \
  --prompt-id <each of the 10 ids> --skip-judge --verbose
```

The v2 run is cached under `runs/qwen_base_prompt_v2/` and does not modify
`QC_Eval_Prompt_Error_Sheet.xlsx`. All 10 generations and 10 QC backtests were
new (one transient Groq HTTP 429, retried once). Gold results are reused from the
baseline summary.

**Judge was skipped** (`--skip-judge`, no Anthropic calls), so there are no
fidelity scores for this condition yet. The baseline random-10 had none either.

## Result

| | Baseline (v1) | Prompt v2 |
|---|---:|---:|
| Completed backtests | 0/10 | 0/10 |
| Runtime errors (initialization) | 10 | 10 |
| Compile errors | 0 | 0 |
| Candidates calling PascalCase `self.` methods | 8 | 0 |
| `api_argument_mismatch` | 1 | 7 |
| `missing_attribute_or_api` | 7 | 2 |
| `undefined_symbol` | 2 | 1 |
| Fidelity (judge) | not judged | not judged |

The prompt fixed what it targeted: PascalCase calls are gone and missing-API
errors fell from 7 to 2. But every candidate still fails in `initialize`, now
mostly because of wrong arguments to real LEAN methods.

## Per prompt

| Prompt ID | v2 status | v2 failure kind | Baseline kind | Main error |
|---|---|---|---|---|
| option-iron-condor-spy_v02 | runtime_error | api_argument_mismatch | api_argument_mismatch | `self.set_warm_up(1, "d")`: resolution given as a string |
| equity-bollinger-mean-reversion_v05 | runtime_error | api_argument_mismatch | missing_attribute_or_api | `self.bb(self.spy, 20, 2, Resolution.DAILY)`: 4th positional arg is `moving_average_type` |
| equity-rsi-overbought-oversold_v04 | runtime_error | api_argument_mismatch | missing_attribute_or_api | `add_equity("QQQ", Resolution.HOUR, DataNormalizationMode.BACKWARDS_RATIO)`: 3rd arg is `market` |
| futures_v05 | runtime_error | api_argument_mismatch | undefined_symbol | `add_future(..., depth=...)`: no such keyword |
| equity-monthly-roc-rotation_v06 | runtime_error | missing_attribute_or_api | missing_attribute_or_api | `equity.set_indicator(roc)` does not exist |
| equity-monthly-roc-rotation_v02 | runtime_error | missing_attribute_or_api | missing_attribute_or_api | `self.time_rules.at_market_open` does not exist (use `after_market_open`) |
| equity-atr-volatility-stop_v09 | runtime_error | api_argument_mismatch | undefined_symbol | `add_equity("SPY", Resolution.MINUTE, DataNormalizationMode.BACKWARDS_RATIO)` |
| equity-bollinger-mean-reversion_v08 | runtime_error | api_argument_mismatch | missing_attribute_or_api | `add_equity(..., data_mapping_mode=...)`: futures-only keyword on an equity |
| equity-bollinger-mean-reversion_v04 | runtime_error | api_argument_mismatch | missing_attribute_or_api | `add_equity("SPY", Resolution.DAILY, DataNormalizationMode.BACKWARDS_RATIO)` |
| option-iron-condor-spy_v07 | runtime_error | undefined_symbol | missing_attribute_or_api | `OptionType` used in a type annotation at class level |

Exact error text, QC project/backtest IDs and source hashes are in
[qc_summary.json](qc_summary.json). Code is in [candidates](candidates), raw model
outputs in [generations](generations), and the terminal log in [run.log](run.log).

## Observations

- Four of seven argument errors put `DataNormalizationMode` / `DataMappingMode`
  into `add_equity` positionally or as an invalid keyword. These enums appear in
  the v2 rules as naming examples; the model treated them as things to pass.
  `bollinger_v05` fails on `bb(..., Resolution.DAILY)` positional, copying the
  rule's example but dropping `resolution=` (`bollinger_v04` has the same line
  but fails earlier on `add_equity`).
- A v3 prompt could state that `resolution` and normalization must be keyword
  arguments, and list the real `add_equity` / `add_future` / `bb` / `set_warm_up`
  signatures. That is still prompt engineering, not fine-tuning, and should be a
  separate condition.
- Zero completed backtests means behavior metrics (fill F1, timing, DTW) are
  unavailable, not zero.
