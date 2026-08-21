# Experiment C — Learnings

## Result: GATE PASS

The objective function works. `validate.py` reads only the Excel workbook (black-box, like a BI tool), computes all 8 criteria from `criteria.json`, prints a PASS/FAIL table, and exits 0/1 so a loop can drive convergence programmatically.

## Two-direction test results (`test_validator.py`)

Direction 1 — every deliberately broken workbook failed its targeted criteria:
| Broken workbook | Mutation | Targeted criteria | Detected |
|---|---|---|---|
| broken_uniform | discounts flattened to ~15% | AC2, AC3, AC5, AC6 | all detected (+AC1, AC7) |
| broken_winrate | win rates forced to 15/40/20/35% | AC1 | detected |
| broken_emea | EMEA premium removed | AC5 | detected |
| broken_sanity | negative price + orphan FK injected | AC8 | detected |

Direction 2 — baseline workbook gets an honest mixed verdict: **3/8 PASS** (AC2, AC4, AC8). Fully consistent with what we observed in Experiment B.

## Bugs found & fixed during testing
1. Dict iterated without `.items()` → string unpacking error (classic).
2. Wrong test expectation: flat 15% discounts *legitimately* pass AC4 (it only forbids dips >1pp, it doesn't require a rise). Lesson: **a criterion checks one claim precisely** — AC4's name says "trend rises" but its implementation only checks dips. Kept as-is (matches signed-off definition) but noted.

## Baseline gap analysis (input to Experiment D)
| Criterion | Actual | Needed |
|---|---|---|
| AC1 win rate | max dev 4.25pp vs 3.0 band | more volume per quarter or seed re-roll |
| AC3 Q4 discount | 22.34% vs 18±2 | lower `base_by_quarter` Q4 (~-3 to -4pp) |
| AC5 EMEA premium | +0.33pp vs +5pp | much stronger EMEA H2 base offsets |
| AC6 EOQ effect | +4.94pp vs +5pp | barely misses — tiny boost increase or noise reduction |
| AC7 realized/list | 78.1% vs 82±2 end | follows automatically once AC3 is fixed |

Key insight: AC6 missing by 0.06pp shows tolerances are neither trivially loose nor impossibly tight — good calibration for testing convergence.
