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
- Runtime errors from passing `Resolution` as a positional argument: 0 in-sample vs. 25 on the held-out set.
