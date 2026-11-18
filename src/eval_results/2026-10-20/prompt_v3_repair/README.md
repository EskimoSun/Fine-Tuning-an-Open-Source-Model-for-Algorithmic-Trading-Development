# Prompt v3 + QC-feedback repair

The 4 v3 failures went through the existing repair loop (Qwen only, REPAIR_SYSTEM, at most 3 rounds, no judge). 2 of 4 completed. See the [comparison README](../README.md).

Files: [repair_summary.json](repair_summary.json), and for each prompt `attempt_XX.py` (code from each round), `attempt_XX_request.json` (the exact repair request) and `history.json` (status, QC IDs, orders, error for each round). Terminal log: [repair.log](repair.log).
