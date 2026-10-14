# Fine-Tuning-an-Open-Source-Model-for-Algorithmic-Trading-Development
This is the development repo for the IEOR4511 capstone project. 

What Jared wants

•⁠  ⁠A spreadsheet with prompts on one side and error types on the other.
•⁠  ⁠10 code templates, each written as 10 prompt versions in different personas (quant researcher, high schooler, etc.).
•⁠  ⁠Fable (Claude) generates the gold-standard strategy for each prompt.
•⁠  ⁠Qwen (before fine-tuning) answers the same prompts, and we score it against Fable’s reference.
•⁠  ⁠Fine-tuned results come later. For now we just need the baseline and the scoring workflow.

Scoring

•⁠  ⁠Compile errors: from the QC compile API.
•⁠  ⁠Runtime errors: from the QC backtest.
•⁠  ⁠Fidelity to the prompt (1 to 5): scored by Fable.
•⁠  ⁠Human check on 10 random rows to confirm Fable’s scores are reasonable.

To do

•⁠  ⁠Replace the 10 placeholder templates with QC’s actual templates once we have Martin’s zip.
•⁠  ⁠Get QC API keys and org access from Jared.
•⁠  ⁠Set up a Qwen endpoint (Together or HF) and confirm the exact model ID.
•⁠  ⁠Run a 5-prompt smoke test, then the full baseline.

HOW WE CAN SPLIT THE TASK

- Task 1: Generate the 10 x 10 prompts using Fable (could make this into a workflow)
- Task 2: Qwen/Fable code generation workflow
- Write scoring workflow (take prompt and Qwen generated code, then score)
    - Task 3: LEAN backtesting API (compile error, runtime error)
    - Task 4: Prompt adherence (trading behavior, trade count, interval, Dynamic Time Warping)
- Task 5: Score the 100 results and compile the results into spreadsheet, check for weird scoring
