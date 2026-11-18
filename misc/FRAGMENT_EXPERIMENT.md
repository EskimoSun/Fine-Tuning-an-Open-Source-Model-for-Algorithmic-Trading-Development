# Experiment design: whole algorithms vs. code fragments

Draft for team review. Jared's research question from the Oct 5 meeting:
does a model trained on **whole algorithms** generate better LEAN code than
one trained on **3 to 4 line code blocks**?

## The two training formats

Both are built from the **same** source algorithms, so the only thing that
changes is how each algorithm is cut up.

| | Whole (W) | Fragment (F) |
|---|---|---|
| One training example | prompt -> full algorithm | context + instruction -> next 3-4 lines |
| From one source algorithm | 1 example | ~5-15 examples |
| Teaches | overall structure (initialize, on_data, scheduling) | exact API calls and idioms |

### How a fragment example is built

Take a working algorithm and pick a cut point at a logical unit
(an indicator setup, an order block, a schedule call). The example is:

- **Input:** the strategy description + all code *before* the cut + a one-line
  instruction for the missing piece (e.g. "create a 14-day RSI on QQQ")
- **Target:** the 3-4 lines that were removed

Cut at logical units, not every 4 lines. A random cut produces targets like
half an `if` statement, which teach nothing useful.

## Controlling for the obvious confound

Fragments multiply the example count by ~10x, so F would see far more
training steps. To compare formats rather than data volume, match on
**training tokens**: train W for more epochs (or F for fewer) so both
runs see roughly the same number of target tokens. Report both the
token-matched comparison and the "natural" one.

## Scoring: both models answer both task types

| Eval task | What it measures | Scored by |
|---|---|---|
| **Whole-algorithm generation** (prompts.jsonl) | Can it write a working strategy from scratch? | static checks, compile, backtest, prompt adherence |
| **Fill-in-the-blank** (held-out algorithms with one block removed) | Can it complete a real algorithm correctly? | splice the generated block back in, then compile + backtest; compare trades to the original |
| **Assembled-from-fragments** | Can the F model build a full algorithm piece by piece? | generate block by block with the model's own earlier output as context, then score as whole |

Scoring fill-in-the-blank by **running the spliced algorithm**, not by text
match, matters: `self.rsi(self.qqq, 14)` and `self.rsi(self.qqq, 14, MovingAverageType.WILDERS)`
behave the same, but string matching would mark one wrong.

The cross-over matters most: if F wins on fill-in-the-blank but loses on
whole generation, that's a real finding (fragments teach API usage but not
program structure), and it suggests a **mixed** format as a third arm.

## Arms

1. Base model, no tuning (baseline)
2. W: whole-algorithm SFT
3. F: fragment SFT (token-matched to W)
4. W+F mixed (optional, if budget allows)

Same base model, same LoRA settings, same source algorithms, 3 seeds each.

## Splits

Split by **source algorithm**, never by example. Every fragment from an
algorithm goes in the same fold as that algorithm's whole version, or the
fragment model sees pieces of test algorithms during training.

## Cost

At ~750 tokens per whole example, 70 training algorithms, 3 epochs is
~160K tokens per W run. F is token-matched, so similar. 4 arms x 3 seeds
= 12 runs, which costs tens of dollars on any of the shortlisted platforms.
Backtests for evaluation will cost more than training.

## Open questions for the team

- Who builds the cut-point tool? (AST-based: split at top-level statements
  inside `initialize` / `on_data`.)
- Do we wait for QC's Hugging Face integration (2-3 weeks), as the meeting
  notes say, or run this offline first with the harness and add the
  in-product test later?
- What trade-match tolerance counts as "same behavior" for fill-in-the-blank?
