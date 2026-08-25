# Fly Benchmark Findings

> M5 exit-criterion measurement: unassisted landing rate across all 25
> v1 RevOps stories, flown one-by-one through `syngen fly` against the
> local LLM. Batch cadence: 1 scenario per batch, status pause after
> each. Doctrine: docs/FLIGHT_MODEL.md.

## Fleet scoreboard

| Metric | Value |
|---|---|
| Flown | 7 / 25 |
| Landed unassisted | 1 |
| Escalated at coverage guard | 5 (17, 01, 02, 04, 05) |
| Crashed | 1 (scenario_03) |
| Unassisted landing rate | 14.3% |
| Non-landings killed pre-generation | 6 / 6 |

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


### Batch 2 - scenario_17 (beat carried by whales masks core decline) [HARD CANARY]

**Outcome:** ESCALATED `criteria_coverage`, 217s, zero iterations
(escalated pre-convergence, at the coverage guard).

**Observations:**
- The drafter's FIRST draft was essentially correct: 4 criteria including
  `core_vs_headline_growth` - the exact check this story needs (the
  hand-flown landing used the same one).
- The coverage-guard LLM audit rejected it on two pedantic grounds:
  1. "'closed in the back half' timing claim not captured" - narrative
     detail; the substance (whales drive headline while core declines)
     IS covered.
  2. "no criterion measures ex-outlier revenue as a quarter-by-quarter
     time series" - demands a per-quarter monotonic series when the
     story's computable substance is first->last divergence, which IS
     captured.
- My audit prompt says "Be strict: when unsure mark UNCOVERED" - that
  instruction has no ceiling. Strictness without an equivalence clause
  turns the guard into a false-positive generator on exactly the stories
  whose claims are expressible.
- Escalation message is wrong: "criteria express NONE of the story's
  computable claims" when they covered most of them. Partial-coverage
  escalation mislabeled as total.
- Infra: escalation fires BEFORE Gate 1 persist -> criteria.json never
  written, so "review criteria manually" points at a nonexistent file.

**Failures & classification (PROVISIONAL - Pass 1, no fixes):**
- F5.1 BUG-GUARD-CALIBRATION (family: criteria-quality): coverage audit
  over-strict; rejects semantically equivalent coverage. Candidate fix:
  equivalence clause in coverage_audit prompt + calibrated strictness
  ("uncovered = absent DIMENSION, not imperfect shape").
- F5.2 GAP-AUTOMATION (family: mixture-calculus): genuinely missing
  vocabulary - no per-period cohort-revenue-trend check exists (ex-outlier
  revenue by quarter). Candidate: generic `revenue_trend` check with a
  cohort filter.
- F5.3 INFRA (family: telemetry): partial-coverage escalations report
  "none"; drafted criteria not persisted on guard rejection.

**Actions:** logged only. NO code changes (measurement freeze).

### Batch 3 - scenario_01 (territory/capacity/pipeline combo)

**Outcome:** ESCALATED `criteria_coverage`, 268s, zero iterations.
- Drafter drafted 6 criteria covering nearly everything; ONE claim
  ("pipeline skewed toward early-stage deals") had no matching check ->
  single partial gap killed the flight.
- Genuine vocabulary hole behind it: no stage-distribution-share check
  exists. -> F6.1 GAP-AUTOMATION (family: pipeline-state).

### Batch 4 - scenario_02 (commit on dead/no-engagement deals)

**Outcome:** ESCALATED `criteria_coverage`, 197s, zero iterations.
- Auditor demanded a CONJUNCTION check ("inactive AND stalled") for the
  'dead deals' claim and a forecast-vs-COMMIT divergence check for the
  'risk higher than headline' claim. The hand-flown landing of #2 passed
  2/2 on commit_no_engagement_share alone.
- -> F7.1 BUG-GUARD-CALIBRATION (same family as F5.1): conjunction/
  strictness pedantry escalating partially-covered stories.
- -> F7.2 GAP-AUTOMATION (minor): composite dead-deal check;
  forecast-vs-commit divergence check. Vocabulary notes, not urgent.

### Batch 5 - scenario_03 (SMB entry-mix beat)

**Outcome:** ERROR - unhandled `KeyError: 'sigma'`, 273s.
- GOOD news: the coverage guard worked AS DESIGNED here - initial draft
  rejected (audit wanted max_dip_pp=0 for 'no dips', -1% for a
  direction-only claim), corrective re-draft satisfied it, Gate 1
  passed. Guard strictness CAN converge when the gap is parameter-shape,
  not missing-dimension.
- Crash: drafter wrote deal_size_lognormal as {"medians_by_quarter": ...}
  with NO sigma key. Config validation accepts it; preflight
  (_autocalibrate_coverage -> float(dl['sigma'])) crashes. An LLM-shaped
  input killed the harness instead of becoming a HARD finding.
- -> F8.1 BUG-PREFLIGHT-ROBUSTNESS: sigma-less configs must be caught at
  lint/validation (or defaulted), never crash calibration.
- -> F8.2 INFRA: crash-path reports lose the session reference
  (report['session']=None even though the session folder exists).

---

## PASS-1 SYNTHESIS (after 5 flights - introspection at pause)

### Scoreboard detail

| Scenario | Outcome | Phase | Root cause |
|---|---|---|---|
| 06 | LANDED (after s06 fixes) | converged | - |
| 17 | escalated | coverage guard | F5.1 guard over-strictness (+F5.2 vocab) |
| 01 | escalated | coverage guard | F6.1 vocab hole -> fatal partial gap |
| 02 | escalated | coverage guard | F7.1 conjunction pedantry (+F7.2 vocab) |
| 03 | CRASHED | calibration | F8.1 unhandled KeyError |

### Common denominator (unambiguous)

**4 of 4 non-landings died in the INTAKE/GUARD layer, before a single
dataset row was generated.** The engine, autopilot remedies, and
convergence loop - everything built through iter 5 - have not yet been
stress-tested by the fleet because the newest gate is the bottleneck.
The vacuous-convergence fix (R6) over-corrected: it treats ANY uncovered
sub-claim as flight-fatal, when its original target was ZERO/generic
coverage.

### Architecture gap vs local patch

This is an ARCHITECTURE gap, not a local patch: guards have one binary
knob each (pass / escalate). The flight-model doctrine needs graduated
responses:
PROCEED (log) -> PROCEED-WITH-NOTE (thin coverage declared up front)
-> REDRAFT (bounded) -> ESCALATE (only zero-coverage or unrecoverable).
Concretely: coverage < 100% but above a threshold (e.g., half of
computable claims covered, including every plan/quota claim) should FLY
with uncovered claims recorded as delivered-but-unproven. Vocabulary
holes (auditor cannot name an EXISTING check) are ROADMAP signals, not
flight failures.

### Candidate fixes queue (Pass 3, NOT executed now)

1. Guard graduation policy (architecture): partial coverage flies with
   declared caveats; escalate only on ~zero coverage. Covers F5.1/F7.1.
2. Coverage-audit prompt: equivalence clause + "name an EXISTING check
   or classify as vocabulary-gap" instruction. Shapes F5.1/F6.1/F7.1.
3. Preflight/lint hardening: sigma-less deal_size_lognormal -> HARD
   finding with deterministic default, never a KeyError. Covers F8.1.
4. Error-path telemetry: crash reports must carry the session dir,
   and guard rejections must persist criteria.json. Covers F8.2/F5.3.
5. Vocabulary additions (roadmap, non-blocking):
   stage_distribution_share, cohort revenue_trend, dead-deal composite,
   forecast-vs-commit divergence.

### Batch 6 - scenario_04 (whitespace under-coverage after capacity added)

**Outcome:** ESCALATED criteria_coverage, 257s, zero iterations.
- Two gaps out of six drafted criteria:
  1. 'largest gaps concentrated in NEWLY ASSIGNED Enterprise territories'
     - auditor wants the qualifier verified; narrative detail (hand-flown
     #4 landed with gap_concentration + quota_vs_potential + placement).
     Pedantry sub-type.
  2. 'AEs over-indexed to mature accounts' - genuine vocabulary hole
     (portfolio composition); auditor's suggested check
     (unowned_account_share) was unrelated - hallucinated suggestion.
- -> F9.1 BUG-GUARD-CALIBRATION (qualifier pedantry, family: criteria-quality)
- -> F9.2 GAP-AUTOMATION (portfolio-composition check) + NOTE: auditor
  hallucinates check names when vocabulary lacks one.

### Batch 7 - scenario_05 (forecast miss via slippage)

**Outcome:** ESCALATED criteria_coverage, 254s, zero iterations.
- THREE gaps. First is a LEGITIMATE save: drafter wrote forecast_vs_actual
  target_pct=108 for a claim that says forecast MISSED (= below actual);
  direction inverted. The guard caught a real contradiction.
- Second/third: commit stage-composition claims - vocabulary hole closely
  related to deferred F29 primitive.
- -> F10.1 GUARD-WORKING (evidence the guard adds value when the gap is
  directional/parametric, not missing-dimension)
- -> F10.2 GAP-AUTOMATION: commit stage-composition check (~F29 family).
