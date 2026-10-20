# Prompt v3 on all 100 prompts (in progress)

**Partial snapshot. 81 of 100 are finished.** Generation model `qwen/qwen3.8-27b` via Groq,
`--system v3`, real QC compile + backtest, **no judge** (no Anthropic calls).
Compare with the [2026-10-20 random-10 README](../README.md).

Pending:
- 10 prompts not generated yet (Groq 8,000 tokens/minute rate limit; being generated slowly)
- 9 backtests waiting on QuantConnect's 100-projects-per-day limit
  (7 failed at `projects/create`; 2 failed reading the backtest, probably a one-off glitch)
- Gold backtests for 4 templates without one yet (sixty-forty, momentum decile,
  opening-range breakout, pairs), which also need new QC projects

Current numbers are in [qc_summary.json](qc_summary.json) (`by_split`,
`by_template`, `by_segment`, `by_specificity`, `failure_kinds`, per-row exact
errors and QC IDs). This README will be rewritten when the run is complete.
