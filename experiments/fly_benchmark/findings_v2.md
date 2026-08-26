# Fly Benchmark Findings v2 - M6 P4 Certification

> M6 P4 exit criterion: all 25 v1 RevOps stories re-flown one-by-one
> through `syngen fly` under the domain-pack architecture (graduated
> coverage guard, claim matrix, generated catalogs, entity schemas).
> Batch cadence: 1 scenario per batch, diagnosis pause after each.
> Doctrine: docs/FLIGHT_MODEL.md, docs/DOMAIN_PACKS.md.

**Code state at start:** `7773def` (M6 P3.5 complete).

## Baseline-as-built (FINDINGS_deprecated.md, frozen 2026-08-25)

| Metric | Baseline value |
|---|---|
| Flown | 7 / 25 |
| Landed unassisted | 1 (scenario_06) |
| Escalated at coverage guard | 5 (17, 01, 02, 04, 05) |
| Crashed | 1 (scenario_03) |
| Unassisted landing rate | 14.3% |
| Non-landings killed pre-generation | 6 / 6 |

Expected deltas from the fixes folded into M6: the five guard escalations
should now fly with notes or a single bounded redraft (F5.1/F7.1/F9.1
graduation); scenario_03 should survive preflight via the sigma default
(F8.1); crash reports keep session refs (F8.2); escalations persist
criteria.json (F5.3). Vocabulary holes are roadmap notes, not failures.

## Fleet scoreboard (certification run)

| # | Scenario | Outcome | Phase | vs baseline | Root cause / notes |
|---|---|---|---|---|---|
| 1 | scenario_01 | ESCALATED | convergence (iter 2) | IMPROVED - reached generation for the first time | F11.x below |

---

## Batches

### Batch 1 - scenario_01 (territory design + capacity + pipeline quality combo)

**Outcome:** ESCALATED at convergence (structural failures), 341s, 2
iterations, dataset generated. Criteria: 10 (after one bounded guard
redraft of the initial 8).

**Progress vs baseline:** previously died at the coverage guard
(F6.1 stage-distribution vocab hole, zero rows generated). This time:
- Coverage guard PASSED the story after one corrective redraft - the
  drafter expressed "skewed toward early-stage deals" as `stage_aging`
  stale-share instead of the still-missing stage-distribution check.
  Graduation policy worked exactly as designed.
- Flight reached Gate 1, drafted a simulator, ran deterministic
  recalibration, generated a workbook, and scored REAL iterations:
  6/10 criteria passing on measured data. First time this story ever
  produced a dataset.

**Observations:**
- Deterministic recalibration landed most pipeline-health criteria:
  slippage path solved (+26pp vs >=12pp), staleness reshaped to 36.9%
  vs <=40%, coverage ratios scaled into band.
- Three persistent failures:
  1. AC7 `quota_vs_potential` unit=segment 'Enterprise' target 118%,
     actual 27%. Quota block was drafted by_motion -> quota_plan rows
     carry plan_unit_type=motion; a segment-unit plan/potential ratio
     cannot be raked through motion-dimensioned plans. No remedy ran.
  2. AC8+AC9 `effective_capacity` unit='Enterprise' - capacity block was
     SYNTHESIZED by_territory (6 territory units), so the requested
     segment unit does not exist in capacity_plan. Autopilot LOGGED
     "AC8: solved ramping counts for effective capacity ~82% (unit
     'Enterprise')" yet the validator reports the unit absent - a
     phantom solve: the solver neither created the unit nor detected the
     mismatch.
  3. AC4 `potential_coverage_gap` min_gap_pp=15, actual -1.4pp (pipeline
     slightly OVER-covers top-potential units). No solver attempted
     across either iteration.
- Drafter quality otherwise good: revenue_vs_plan company+segment split,
  coverage_ratio, slippage_trend all correct checks with sane params;
  data_sanity present.

**Failures & classification (logged only - no fixes during certification):**
- F11.1 BUG-AUTOPILOT (family: calibration): `effective_capacity` solver
  reports success for a unit absent from the capacity plan; the
  dimension mismatch (segment criterion vs by-territory synthesis) is
  never detected -> phantom "solved" log line, guaranteed structural
  failure at validation.
- F11.2 BUG-GUARD-CALIBRATION (family: cross-block consistency): nothing
  checks that criterion units exist in the plan dimension the drafted
  config produces (segment-scoped criteria vs motion quotas / territory
  capacity). Exactly the class the new entity schemas could lint
  pre-generation: criterion param space vs schema grain/dimension.
  Candidate fix (post-certification): criteria-vs-schema lint at Gate 1.
- F11.3 GAP-AUTOMATION (minor, family: whitespace-calculus): no autopilot
  remedy for `potential_coverage_gap`; failure persisted unchanged
  through both iterations.
- NOTE (roadmap, not a failure): stage-distribution vocabulary hole
  (F6.1) remains open; the drafter routed around it via stage_aging.

**Actions:** logged only. NO code changes (certification run in progress).

