# Experiment F — Session Tweak Loop

## What this is
Tests the "come back later, tweak the story slightly" workflow end-to-end:
1. Start from the converged Experiment D session (8/8 PASS).
2. Present an amended story: *"Q4 discounts worsened further (~21% average); EMEA still the worst offender; the dataset should also cover our CSB segment."*
3. Classify the diff: **parametric** (Q4 discount curve) vs **taxonomy addition** (CSB segment).
4. Adjust ONLY simulator.json knobs (+ amend AC3 target in criteria) — zero generator code changes.
5. Regenerate and verify: **identical structure** (same sheets/columns), **different values**, all amended criteria PASS.

## Why it matters
This is the retention/replay promise of the product: datasets are living artifacts driven by versioned configs, not one-shot outputs. If a small story edit forces structural rework, the config-driven architecture claim fails.

## Pass condition
- Same workbook structure (sheet names + column names identical to baseline)
- CSB segment present in accounts/opportunities
- Amended criteria 8/8 PASS
- Only simulator.json + criteria.json changed

## Artifacts
- `session/simulator.json` — tweaked config (from D's converged baseline)
- `criteria_amended.json` — AC3 target moved 18% → 21%
- `structure_check.py` — proves structure identity between baseline and tweaked workbooks
- `iterations_log.md`, `learnings.md`
