# Fly Benchmark Findings

> M5 exit-criterion measurement: unassisted landing rate across all 25
> v1 RevOps stories, flown one-by-one through `syngen fly` against the
> local LLM. Batch cadence: 1 scenario per batch, status pause after
> each. Doctrine: docs/FLIGHT_MODEL.md.

## Fleet scoreboard

| Metric | Value |
|---|---|
| Flown | 1 / 25 (scenario_06: v1 escalated, v2 after fixes LANDED) |
| Landed unassisted | 1 |
| Escalated | 0 |
| Unassisted landing rate | 100.0% (n=1, post-fix) |

---

## Batches

### Batch 1 - scenario_06 (Ent missed / MM beat via quota-vs-potential)

**Outcome:** ESCALATED at iteration cap (10), 422s. Criteria: Enterprise
~95%, Mid-Market ~104%, company ~100%, Ent plan ~120% of potential,
MM plan ~40% of potential.

**Observations:**
- Drafter did well: correct blocks, sensible criteria, plausible plans.
- Pre-flight calibration set unit attainments correctly, then its OWN
  company-wide branch stomped them back to 1.00 -> raking pinned all
  segments to exactly 100% (iter 2 table shows 100.00% everywhere).
- AC4/AC5 (quota_vs_potential) were UNFIXABLE inside the loop: plan
  levels are plan-of-record (blocked paths, G14) and market potential is
  generated data. The proposer kept proposing attainment turns that could
  never touch them; burned the whole iteration budget on them.
- Oscillation on AC1/AC2/AC3 evaded stall detection (scores changed every
  proposal even though best-partial never improved after iter ~3).
- Power cut lost fly_report.json + per-scenario report (write ordering).

**Failures & classification:**
- D1 BUG (missing automation): `_autocalibrate_planning` company-wide
  branch overwrote criterion-pinned unit attainments. -> FIXED:
  branch now fills only units no criterion named.
- D2 MISSING AUTOMATION: no solver for quota_vs_potential. -> FIXED:
  new autopilot remedy A2 `_remedy_quota_potential` - reads the generated
  workbook's accounts sheet and scales named units' plan curves so
  sum(targets)/sum(potential) lands exactly on target_ratio_pct.
  Closed-form against measured data; one shot per session.
- D3 GAP: oscillation evaded stall detection. -> FIXED: new
  `since_improve` guard escalates after 6 iterations without net score
  improvement ("oscillating" reason with named margins).
- D4 INFRA: report write happened after console print; power cut between
  them lost records. -> FIXED: persist before printing.

**Actions:** all four fixed with regression tests
(test_bench_s06_fixes.py, 274 total green). scenario_06 re-flown as the
verification flight.

**Verification re-fly:** CONVERGED, 2 iterations, 223s, **0 LLM
proposals** - the entire flight was deterministic (pre-flight calibration
+ autopilot remedies); the LLM's only work was drafting criteria and the
config. fly_report.json persisted correctly this time. Notable drafter
behavior: first draft put a list where quota.attainment wanted a scalar -
the deterministic repair path caught it and the corrective re-draft
recovered without human help.

---

