# Fine-tuning pipeline (training data + Together AI LoRA)

The 100 eval prompts and the 10 gold templates in `data/templates/` are **test-only**. Nothing here trains on them.

## Training data (v1)

| Source | Where | Target answer |
|---|---|---|
| QuantConnect's own project templates (89, Apache 2.0), minus the 10 eval ones | `data/train_templates/<folder>/main.py` | the template's `main.py` (written and tested by QC) |
| Hand-written requests for those templates (individual / startup / institutional styles) | `data/train_prompts_src.txt` | same |
| Each template's own description and spec from QC's `templates.json` | `data/train_templates/templates_meta.json` | same |
| QuantConnect Writing Algorithms FAQ (question → answer) | `data/qc_faq_writing_algorithms.md` | FAQ answer (separate system prompt) |

Copied from [QuantConnect/Documentation](https://github.com/QuantConnect/Documentation) at commit `72caf31` (2026-11-04).

Leakage guard (`build_dataset.py`): eval templates are excluded by folder, every prompt is compared with the 100 eval prompts (token Jaccard, max 0.6), and every code target with the 10 gold templates (line-level difflib, max 0.8). Whole templates are held out for validation (about 10%).

Code examples use the eval pipeline's v1 system prompt, so the tuned model is tested without the long v3 prompt.

## Steps

All commands run from `src/`.

```bash
# 1. Check each training template still backtests on QC (one reused project, no daily-cap use)
python -m finetune.validate_qc

# 2. Build train/val JSONL (keep only QC-passing templates)
python -m finetune.build_dataset --require-qc      # -> finetune/out/{train,val}.jsonl, manifest.json

# 3. LoRA on Together (needs TOGETHER_API_KEY in .env, `pip install together`)
python -m finetune.together_finetune start          # default Qwen/Qwen3.5-4B, 3 epochs, lr 1e-4
python -m finetune.together_finetune status

# 4. Evaluate (dedicated endpoint, billed per minute; undeploy right after)
python -m finetune.together_finetune deploy
QWEN_BASE_URL=https://api.together.xyz/v1 QWEN_API_KEY=$TOGETHER_API_KEY QWEN_TUNED_MODEL=<name> \
  python -m qc_eval.pipeline --models qwen_tuned --skip-judge
python -m finetune.together_finetune undeploy
```

For a fair comparison, also run the untuned 4B (`qwen_base` with `QWEN_BASE_MODEL=Qwen/Qwen3.5-4B`) on the same 100 prompts. The existing baseline is 27B on Groq.

## Next data sources (not built yet)

- Repair pairs: run untuned 4B on the training prompts, keep (broken code + QC error → fixed code).
- More ATR / momentum / pairs variants (new tickers and parameters), each kept only if it passes QC.
- "QuantConnect can do this" examples for shorting, index constituents and option data (the 5 false refusals).
