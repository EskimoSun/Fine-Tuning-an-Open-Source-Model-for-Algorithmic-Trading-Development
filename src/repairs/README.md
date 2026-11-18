# Reviewed repairs of failed Qwen strategies

These files are manually repaired derivatives, not unmodified Qwen baseline
outputs. Original generations and failed QC evaluations remain under
`runs/qwen_base/` and `runs/scoring/evaluations/qwen_base/`.

The three available repairs are for RSI prompt versions 01, 02 and 04. Their
manifest binds each repaired file to the SHA-256 of its exact original source;
packaging fails if that original has changed. Each new record carries
`intervention: manual_code_repair`, its source hash and a list of changes.

From `src`, package the reviewed files and evaluate them as a separate model label:

```bash
python -m qc_eval.prepare_repairs
python -m qc_eval.score --models qwen_repaired --limit 5 --qc
```

Versions 03 and 05 have no repairs; they will show `missing_generation` rather
than silently substituting a different strategy. Add `--judge` only if you also
want a separately paid fidelity judgment on the repaired code.

Changes:

- All variants use the snake_case QC API and `Resolution.HOUR`. Private fields
  such as `_symbol` and `_rsi` avoid shadowing QCAlgorithm factory/helper methods.
- v01 and v02 use `self.rsi(symbol, 14, MovingAverageType.WILDERS, Resolution.HOUR)`.
  The unused placeholder SMA in v01 is removed. The nonexistent `Indicator` call
  in v02 is replaced with the RSI helper.
- v04 dispatches trading from hourly `on_data`; the original scheduled event
  was daily at market open with the wrong callback signature. Its history is
  explicitly typed as `TradeBar` so bar closes can be read correctly. The
  simple-average RSI arithmetic and Q4 date range remain as generated.
- The original strategies' different exit rules and date ranges remain. v01
  exits/reverses at RSI extremes, v02 exits at the midline, and v04 uses inclusive
  midline exits. Repairs therefore do not force all variants to match the gold.

The offline contract tests exercise initialization, readiness guards and selected
entry/exit paths. They are not a substitute for a QC cloud backtest. In particular,
v01/v04 retain different date ranges from the gold template, so the scorer will
leave equity DTW unavailable until a separately defined common-window comparison
is used; fixing an API call does not establish full behavioral equivalence.

API references:
[RSI](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/relative-strength-index),
[typed history](https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/history-responses),
[event handlers](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/event-handlers).
