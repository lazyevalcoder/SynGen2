# Experiment B — Learnings

## Result: GATE PASS

Architecture proven: one fixed `generate.py` (~200 lines) + hand-authored `simulator.json` produces the multi-sheet Excel workbook. No LLM involved in generation — that's the point.

## Verification results (`verify_b.py`)
| Check | Result |
|-------|--------|
| Determinism (same seed → identical data across runs) | PASS |
| Knob change (`noise_sd_pp` 3→8) changes output without code edits | PASS (discount sd 4.68 → 8.78 pp) |
| AC8 data sanity (bounds, positive amounts, FKs, dates in quarter) | PASS |

## Distribution eyeball (baseline config)
- Discounts rise Q1→Q4 in every region; EOQ deals discount ~5pp deeper than mid-quarter (19.8% vs 15.0%) — story shape is present.
- Deal sizes: median ~$44.5k, p10 ~$12.6k, p90 ~$119.7k — plausible lognormal spread.
- Workbook opens cleanly with `accounts` / `opportunities` / `quarterly_summary` sheets.

## Learnings for Experiments C & D
1. **Baseline misses some criteria** — expected and fine:
   - Win rate Q2 hit 33% vs annual mean ~28.75% (>3pp band). Binomial noise at n=100/quarter has std ≈4.4pp — **the ±3pp AC1 tolerance is tight relative to sample noise**. Options for D: raise `per_quarter`, or accept occasional re-rolls via seed change.
   - Q4 avg discount landed 22.3% vs target 18±2. Root cause: base blend (~18.9) + EOQ boost average contribution (~+1.5pp since 30% of deals sit in the window) + clip-at-0 skew. Knob fix available: lower `base_by_quarter` Q4 values to compensate.
   - Realized/list Q4 = 78% vs 82±2 — same root cause as above.
2. **Regional criteria are noisy**: only ~27 won deals/quarter split across 3 regions → ~8 EMEA won deals. EMEA's H2 premium flickers (it was lowest in Q3 this run). For D: either increase volume, strengthen EMEA base offsets, or evaluate AC5 on all deals rather than won-only.
3. **Knobs interact**: EOQ boost inflates quarterly averages — single-knob reasoning won't converge; that's precisely why the loop exists.
4. xlsx files embed timestamps → determinism must be checked on **data**, not file bytes (handled in `verify_b.py`).
