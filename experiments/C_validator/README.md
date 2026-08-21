# Experiment C — Validation Script (The Objective Function)

## What this is
A `validate.py` script that reads the acceptance criteria from Experiment A plus the generated Excel workbook from Experiment B (`output/syngen_demo.xlsx`), computes each metric, and prints a pass/fail table with actual vs target vs tolerance.

## Why it matters
Without an automated checker, the simulate loop has no signal. This script IS the objective function for Experiment D and eventually for the harness's convergence loop.

## Method
- `validate.py <data_dir> <criteria_file>` → per-criterion PASS/FAIL table + overall verdict.
- Tested in BOTH directions:
  - Against compliant data → all green.
  - Against deliberately broken data (e.g., uniform deal sizes, no concentration) → relevant checks fail.

## Pass condition
Validator correctly passes good data AND correctly fails broken data. No human judgment required to interpret results.

## Gate
Without this passing both ways, Experiment D's convergence loop is meaningless.
