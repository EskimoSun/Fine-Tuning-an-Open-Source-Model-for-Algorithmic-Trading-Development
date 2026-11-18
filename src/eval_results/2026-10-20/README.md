# Evaluation snapshot: 2026-10-20 (prompt engineering)

Same 10 prompts as the original baseline (seed 42,
[manifest](../2026-10-19/baseline_random10/manifest.json)), same generation model
(`qwen/qwen3.8-27b` via Groq, temperature 0), real QC compile + backtest. Only the
system prompt changes between conditions. The original baseline is unchanged and
`QC_Eval_Prompt_Error_Sheet.xlsx` was not modified.

**No judge was run** (`--skip-judge`, no Anthropic calls), so there are no
fidelity scores. A completed backtest proves the code runs, not that it follows
the request.

## Conditions

| Condition | What changes | Folder |
|---|---|---|
| Baseline (v1) | original `SYSTEM` | [../2026-10-19/baseline_random10](../2026-10-19/baseline_random10) |
| Prompt v2 | `SYSTEM_V2`: snake_case / enum / import rules | [prompt_v2_random10](prompt_v2_random10) |
| Prompt v3 | `SYSTEM_V3`: keyword-only optional arguments, real LEAN signatures, scheduling and options/futures rules | [prompt_v3_random10](prompt_v3_random10) |
| Prompt v3 + repair | v3 failures sent through the existing QC-feedback repair loop (Qwen only, `REPAIR_SYSTEM`, up to 3 rounds) | [prompt_v3_repair](prompt_v3_repair) |

```bash
cd src
python -u -m qc_eval.pipeline --models qwen_base --system v3 --prompt-id <id> ... --skip-judge --verbose
python -u -m qc_eval.pipeline --models qwen_base --system v3 --repair-attempts 3 --prompt-id <failed id> ... --verbose
```

## Result

| | Baseline | v2 | v3 | v3 + repair |
|---|---:|---:|---:|---:|
| Completed backtests | 0/10 | 0/10 | **6/10** | **8/10** |
| Candidates calling PascalCase `self.` methods | 8 | 0 | 0 | 0 |
| Fidelity (judge) | not judged | not judged | not judged | not judged |

## Per prompt

Orders / closed trades. Gold values are from the baseline Gold backtests.

| Prompt ID | Gold | Baseline | v2 | v3 | v3 + repair |
|---|---|---|---|---|---|
| equity-bollinger-mean-reversion_v04 | 4 / 2 | error | error | **4 / 2** | (not needed) |
| equity-bollinger-mean-reversion_v05 | 4 / 2 | error | error | **4 / 2** | (not needed) |
| equity-bollinger-mean-reversion_v08 | 4 / 2 | error | error | **4 / 2** | (not needed) |
| equity-monthly-roc-rotation_v02 | 110 / 71 | error | error | **100 / 64** | (not needed) |
| option-iron-condor-spy_v07 | 132 / 64 | error | error | **84 / 28** | (not needed) |
| futures_v05 | 5 / 2 | error | error | **2 / 1** | (not needed) |
| equity-monthly-roc-rotation_v06 | 110 / 71 | error | error | error | **30 / 18** after 1 repair |
| equity-rsi-overbought-oversold_v04 | 22 / 11 | error | error | error | **37 / 18** after 3 repairs |
| equity-atr-volatility-stop_v09 | 17905 / 8952 | error | error | error | error after 3 repairs |
| option-iron-condor-spy_v02 | 132 / 64 | error | error | error | error after 3 repairs |

Remaining failures:

- **atr_v09**: each repair fixed one runtime error and hit the next one. The
  sequence was `bar.is_trade` → `add_plot_series` → `add_series` arguments → `plot`
  arguments. All of these are in the plotting and bar-handling code the prompt
  asks for "for audit".
- **iron_condor_v02**: all four rounds fail on the same line,
  `self.option_chains.get(...)` inside a scheduled callback (`option_chains` is a
  method on the algorithm, not a dict). The repair model never changed it.

Order counts that differ from Gold are not errors in themselves: rules, timing
and dates can differ. They need the judge or the behavior comparison (`qc_eval.score`)
before anyone calls a candidate correct.

## Caveats

- v3's rules were written **after seeing v2's errors on these same 10 prompts**,
  so v3 is tuned on the evaluation set and its 6/10 is optimistic. The rules are
  generic LEAN API facts with no prompt text or gold code. They should still be
  re-checked on the other 90 prompts before comparing against fine-tuning.
- Every API example in `SYSTEM_V3` ran in a QC probe backtest
  ([prompt_v3_random10/api_probe.py](prompt_v3_random10/api_probe.py), project
  38187720, backtest f662fc85b979b0561e3a7eafc6cb9daa, completed, 6 orders). The
  probe caught two wrong guesses before v3 was used: `macd` takes `type=`, not
  `moving_average_type=`, and `set_warm_up(n, Resolution.DAILY)` fails with an
  hourly indicator.
- Groq returned HTTP 429 several times. Runs were resumed and no successful
  generation was resampled.
- The repair condition is a separate intervention: it gets real QC errors and
  extra rounds, so it is not comparable to a single-shot model.
