# Experiment F — Iterations Log

## Baseline
Experiment D's converged session: 8/8 PASS, seed 42, 3-segment world.

## Story amendment presented
> *"Q4 discounts worsened further (~21% average); EMEA still the worst offender; the dataset should also cover our CSB segment."*

## Diff classification
| Change | Type | Artifact touched |
|--------|------|-----------------|
| Q4 discount curve deeper | Parametric | simulator.json base_by_quarter (AMER/APAC 15.5→17.5, EMEA 22→24) |
| CSB segment exists | Taxonomy addition | simulator.json segments weights (+CSB 0.12) |
| AC3 target 18→21% | Criteria amendment | criteria_amended.json |
| AC7 end target 82→79% | **Implied amendment** (100−21≈79) | criteria_amended.json |

## Iteration 1 result: 7/8 PASS
AC7 failed on the first run because the initial amendment updated AC3 but not AC7. Root cause: **criteria dependencies** — changing one target mathematically invalidates another. The diff classifier must propagate implied amendments.

## Iteration 2 result: 8/8 PASS — STORY LANDED (exit 0)
After propagating AC7's implied end-target change.

## Structure verification (structure_check.py)
- Sheets + columns identical to baseline: True
- CSB present: 9 accounts, 239 opportunities
- Values changed: Q4 avg discount 19.16% → 21.16%
- Generator code changes required: **zero**
