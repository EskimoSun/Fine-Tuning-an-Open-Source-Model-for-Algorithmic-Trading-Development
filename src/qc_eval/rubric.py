"""Shared prompt-adherence rubric for both evaluation commands."""

FIDELITY_RUBRIC = """Score fidelity to the request from 1 to 5:
5 = every requested asset, indicator, parameter, entry/exit rule and date range is present and correct
4 = all key elements present; one minor detail off
3 = core idea right but one key element wrong or missing
2 = same strategy family, several key elements wrong
1 = does not implement the requested strategy
If the request is vague, judge whether the code is a sensible version of it; do not penalize choices the request left open.
Judge only what the code does, not style. Do not assume it runs."""
