# qwen_tuned_9b_insample_2026_11_18

In-sample evaluation of the fine-tuned 9B model (final checkpoint, `fulldataplusfaq` LoRA), run on 2026-11-18.

## Setup

- Prompts: 87, one per training template (in-sample)
- System prompt: v1
- Thinking: off
- `max_tokens`: 8192
- No repair loop, no LLM judge
- One JSON file per prompt, same format as the other folders in `src/runs/`

## Results (QuantConnect backtest status)

| Run | Prompts | Completed | Runtime error | Compile error | No code | Success rate |
|---|---|---|---|---|---|---|
| In-sample (this run) | 87 | 81 | 6 | 0 | 0 | 93% |
| Held-out rerun (2026-11-16) | 100 | 14 | 81 | 5 | 0 | 14% |

By template split (assuming the training/validation split matches `finetune/out/manifest.json`):

- 78 trained templates: 77/78 completed
- 9 validation templates: 4/9 completed

Notes:

- 21 of the 81 completed backtests placed 0 trades.
- Runtime errors from passing `Resolution` as a positional argument: 0 in-sample vs. about 25-29 on the held-out set, depending on how the QC error text is matched (a static signature check finds 27 call sites in `rsi`/`bb`/`atr`).

## Runtime errors (6)

5 of the 6 failures are on validation templates; 1 is on a trained template.

| Prompt | Split | Error | Cause |
|---|---|---|---|
| `cfd_v01` | validation | `name 'BaseConsolidatedBar' is not defined` | Type hint uses a class that does not exist, so the module fails to import. |
| `chained-universe_v02` | validation | `'Equity' object has no attribute 'fundamental'` | Should be `security.fundamentals`. |
| `crypto-static_v06` | validation | `object has no attribute 'add_crypto_pair'` | Non-existent method; the correct call is `add_crypto`. |
| `equity-adx-trend-filter_v07` | trained | `object has no attribute 'indicators'` | Reads `self.indicators["SPY12"]`, a dictionary that is never defined. |
| `equity-dual-momentum-asset-class_v04` | validation | `name 'ETF' is not defined` | Type hint `List[ETF]` uses an undefined name, so the module fails to import. |
| `warmup-template-rolling-window_v07` | validation | `Unable to create SPY consolidator because SPY is registered for Daily data` | Subscribes SPY at Daily resolution, then tries to build minute bars from it. |

All six are hallucinated API names or logic errors. None is the `Resolution` positional-argument error.
