# Experiment D — Learnings

## Result: GATE PASS — converged in 2 iterations

The full chain works end-to-end:

**Story -> acceptance criteria -> simulator.json knobs -> generated Excel -> validator 8/8 green (exit 0)**

Final workbook: `../B_config_generator/output/syngen_demo.xlsx` (1,600 opportunities, 60 accounts, deterministic seed 42). Re-verified determinism and knob responsiveness after convergence.

## Iteration history
| Iter | Changes | Result |
|---|---|---|
| Baseline | — | 3/8 PASS |
| 1 | volume 100->400/qtr, boost 5->5.5, base curves re-shaped, EMEA H2 premium forced | 7/8 PASS |
| 2 | boost 5.5->6.5, Q1 bases 12->11.5 (compensate stacking) | **8/8 PASS** |

## What we learned

### 1. Knob math is predictable
After iteration 1's calibration, every outcome was predicted within ~0.5pp using a simple model:
`expected_won_avg = blend(base_by_quarter, region_mix) + eoq_share x boost + clip_bias`
This predictability is exactly what makes automating the loop later straightforward — an agent (or even gradient-free optimizer) can reason with this transfer function.

### 2. Structural vs statistical criteria behave differently
- **AC1 (win rate flat)** could NOT be fixed by discount knobs at n=100/quarter — binomial noise (std ~4.4pp) exceeded the ±3pp band. The fix was *volume* (`per_quarter` 400), not tuning.
- Lesson for the harness: classify criteria as **statistical** (need sample size / seed re-rolls) vs **parametric** (need knob shifts) before iterating.

### 3. Knobs stack — compensation is required
Raising the EOQ boost inflated Q1's average past AC2's ceiling; fixed by lowering Q1 bases. Single-criterion greedy adjustment would have oscillated. The loop needs multi-criterion awareness (or small, simultaneous compensating moves).

### 4. Thin margins exist
Final pass margins: AC5 +0.03pp over threshold, AC6 +0.77pp. A different seed could flip them. For production use: either target mid-band rather than threshold-edge, or make the validator report margin so the loop keeps going while thin.

### 5. Revenue-weighting surprise
AC7 (realized/list) runs ~+1.8pp above the simple-average prediction because realized/list weights deals by size. Metric definitions carry hidden weighting semantics — the harness's spec phase should pin these down explicitly (we did, in `acceptance_criteria.md`).

### 6. Tooling friction found
- PowerShell `Set-Content -Encoding UTF8` writes a BOM that breaks `json.load` — config edits should go through BOM-safe tooling.
- Validator must run from its own directory or take absolute paths (relative default paths bit once).

## What this proves for the full project
1. Stories CAN be landed by parameter steering — the core SynGen thesis is validated manually.
2. The loop is automatable: validator exit code + predictable knob transfer function + 2-iteration convergence = trivial work for an agent.
3. Config-driven architecture survived contact with real iteration without needing code changes — only JSON changed across all iterations.

## Next steps (full build, in order)
1. Generalize generator beyond hardcoded schema (entities/fields from spec)
2. Automate the convergence loop (agent reads validator output, proposes knob deltas)
3. Persona-based spec critique (Phase 2) feeding criteria.json
4. Second story/domain to test generalization
