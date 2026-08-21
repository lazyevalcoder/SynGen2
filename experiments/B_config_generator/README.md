# Experiment B — Hand-written simulator.json + Fixed Generator

## What this is
Proof that **config-driven generation** works: one hand-authored `simulator.json` (the constraint/knob engine) plus ONE fixed Python generator script that reads it and emits the dataset. No LLM codegen per run.

## Why it matters
LLM-generated generator scripts break silently. A fixed engine + JSON knobs means reproducibility, tweakability, and testability. This architecture must be proven before any agent touches it.

## Artifacts
- `simulator.json` — entities, counts, distributions, discount parameters, time model, seed.
- `generate.py` — fixed interpreter (~200 lines), numpy/pandas/openpyxl only.
- `output/syngen_demo.xlsx` — single workbook, multi-sheet: `accounts`, `opportunities`, `quarterly_summary`.

## Hardcoded assumptions (documented, not hidden)
- Time horizon: FY26 Q1–Q4
- Regions: AMER, EMEA, APAC
- ~60 accounts, ~400 opportunities (~100/quarter)

## Pass condition
Output opens cleanly as CSVs; distributions look sane; changing a knob in `simulator.json` visibly changes the output without touching code.

## Gate
If config-driven generation produces plausible data → proceed to Experiment C.
