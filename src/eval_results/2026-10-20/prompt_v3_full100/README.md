# Prompt v3 on all 100 prompts (INTERIM)

**Interim snapshot: 81 of 100 finished.** Generation model `qwen/qwen3.8-27b` via
Groq, `--system v3`, real QC compile + backtest, **no judge** (no Anthropic calls),
so no fidelity scores. A completed backtest proves the code runs, not that it
follows the request. Compare with the [random-10 README](../README.md).

## Pending

- 10 prompts not generated yet: pairs v05/v06/v08, futures v03/v04/v06/v07,
  iron condor v06/v09/v10. Groq's limit is 8,000 tokens per minute; these are
  being generated slowly.
- 9 backtests waiting on QuantConnect's 100-projects-per-day limit: atr v06,
  iron condor v08, opening-range v06/v08, pairs v02/v03/v10, futures v01/v02.
  Seven failed at `projects/create`; atr v06 and iron condor v08 failed while
  reading the backtest result (likely transient).
- Gold backtests for 4 templates without one yet (sixty-forty, momentum decile,
  opening-range breakout, pairs). These also need new QC projects.

## Results so far

17 completed out of 100 (81 finished).

| Split | Completed |
|---|---:|
| 10 prompts v3 was tuned on | 6/10 |
| 90 held-out prompts | 11/90 (19 still pending) |

The held-out rate is far below the tuned-on rate, so v3's 6/10 on the random
sample does not generalize.

| Template | Completed /10 |
|---|---:|
| Bollinger mean reversion | 8 |
| Monthly ROC rotation | 2 |
| RSI overbought/oversold | 2 |
| Futures (ES continuous) | 2 |
| 60/40 portfolio | 1 |
| Opening-range breakout | 1 |
| SPY iron condor | 1 |
| ATR volatility stop | 0 |
| Momentum cross-sectional decile | 0 |
| Pairs cointegration | 0 |

| Specificity | Completed |
|---|---:|
| ceiling (reference) | 5/10 |
| precise | 7/30 |
| vague | 4/30 |
| over_specified | 1/30 |

By segment: individual 4/30, startup 3/30, institutional 5/30, reference 5/10.

## Failure kinds (59 runtime errors, 5 refusals)

| Kind | Count | Examples |
|---|---:|---|
| missing_attribute_or_api | 35 | bar is None → `'NoneType' object has no attribute 'close'` (4); `Slice.contains`; `portfolio.portfolio_value`; `time_rules.at_market_open`; `TradeBar.is_trade`; `self.option_chains.get` |
| api_argument_mismatch | 10 | `add_future(..., extended_market_hours=<int>)`; `plot(<indicator>)` where a series-name string is required; `add_universe_selection(<function>)` |
| undefined_symbol | 5 | `name 'rsi' is not defined` (4) |
| other_runtime_error | 5 | a list assigned to `self.universe_settings`-type base members (2); `UniverseSettings` called as a function; `len()` on the `option_chains` method; formatting `None` |
| python_exception | 3 | `KeyError` on `'SPY'` and on an unmapped key in a collection; `range` minus `int` |
| null_reference | 1 | futures v08: `Object reference not set to an instance of an object` |
| declined_no_code | 5 | see below |

The model wrongly declined 5 feasible requests, claiming QC lacks something it has:

- rsi_v09: "QQQ cannot be shorted"
- momentum_v01, momentum_v04: "no S&P 500 constituent data"
- iron_condor_v01: "no historical SPY option chains"
- iron_condor_v04: "no 10-day expirations"

## Orders / closed trades vs Gold (held-out completed)

| Prompt | Candidate | Gold |
|---|---|---|
| rsi v02, v10 | 22 / 11 | 22 / 11 |
| bollinger v01, v02, v07, v10 | 4 / 2 | 4 / 2 |
| bollinger v09 | 6 / 3 | 4 / 2 |
| futures v10 | 5 / 2 | 5 / 2 |
| roc v08 | 100 / 64 | 110 / 71 |
| sixty-forty v10 | 6 / 2 | pending |
| opening-range v10 | 168 / 84 | pending |

## Files

[qc_summary.json](qc_summary.json) has `by_split`, `by_template`, `by_segment`,
`by_specificity`, `failure_kinds`, and per-row exact errors, QC project/backtest
IDs, decline text and Gold references. Also [candidates](candidates),
[generations](generations) and the terminal log [run.log](run.log).

One diagnostic Groq request for pairs v05 was sent by hand to inspect rate-limit
headers. Its output was not saved; only the pipeline's cached generation will be
used. This README will be rewritten when the run is complete.
