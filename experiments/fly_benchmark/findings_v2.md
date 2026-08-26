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
| 2 | scenario_02 | CRASHED | simulator draft | NEW FAILURE MODE (baseline: guard escalation) | F12.1 below |
| 3 | scenario_03 | ESCALATED | convergence (proposal cap 8, iter 10) | IMPROVED - sigma crash gone, ran full loop to 8/11 | F13.x below |
| 4 | scenario_04 | ESCALATED | preflight calibration | IMPROVED - passed guard, died later at preflight | F14.1 below |
| 5 | scenario_05 | **LANDED** | converged iter 2 | **IMPROVED - first cert landing** (baseline: guard escalation) | - |
| 6 | scenario_06 | ESCALATED | convergence (iter cap 10) | REGRESSION vs baseline post-fix landing | F15.x below |
| 7 | scenario_07 | ESCALATED | oscillation guard (6 stale iters) | new flight (not in Pass 1) | F16.x below |
| 8 | scenario_08 | ESCALATED | convergence (proposal cap 8) | new flight (not in Pass 1) | F17.x below |
| 9 | scenario_09 | **LANDED** | converged iter 7 | new flight (not in Pass 1) - autopilot block synthesis carried | - |
| 10 | scenario_10 | ESCALATED | convergence (structural x3) | new flight (not in Pass 1) | F18.x below |

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


---

### Batch 2 - scenario_02 (commit concentrated in no-engagement deals)

**Outcome:** CRASHED at simulator draft, 214s, zero iterations.
`AttributeError: 'list' object has no attribute 'items'`.

**Progress vs baseline:** previously ESCALATED at the coverage guard
(F7.1 conjunction pedantry + F7.2 vocab). This time the graduated guard
accepted the story after one corrective redraft - single criterion
`commit_no_engagement_share min_share_pct=40` - and Gate 1 passed. The
guard is no longer blocking this story.

**Observations:**
- Crash site: `draft_simulator` -> `validate_simulator_doc`. Reproduced
  deterministically: when the drafter writes an accounts dimension as a
  LIST (e.g. `"regions": ["AMER", "EMEA"]` instead of a weight map),
  config.py:166 (`cfg["accounts"].get(dim, {}).items()`) raises
  AttributeError - not a ConfigError - which escapes the ConfigError-only
  handler in spec.py and kills the flight. Confirmed by synthetic repro:
  list-valued regions/segments both produce the exact error string;
  industries-as-map validates fine.
- Same failure family as F8.1: an LLM-shaped input kills the harness
  instead of becoming a HARD finding + corrective re-draft. F8.1 fixed
  the sigma instance; the general class (type-shape mismatches inside
  validate_simulator_doc raising AttributeError/TypeError instead of
  ConfigError) remains open.
- Infra positives verified under crash: fly report CARRIES the session
  reference (F8.2 fix working), FLIGHT CRASH line written to
  session_log.md, criteria.json persisted.

**Failures & classification (logged only - no fixes during certification):**
- F12.1 BUG-PREFLIGHT-ROBUSTNESS (family: input-hardening, F8.1
  generalized): validate_simulator_doc raises raw AttributeError/TypeError
  on type-shape deviations (list where mapping expected) in at least
  accounts.regions / accounts.segments paths; draft_simulator only
  catches ConfigError so the session dies instead of corrective
  re-drafting. Candidate fix (post-certification): shape-guard dimension
  blocks at validation entry (raise ConfigError naming the block), or
  broaden the repair path.

**Actions:** logged only. NO code changes (certification run in progress).

---

### Batch 3 - scenario_03 (SMB beat via cheap entry-tier volume)

**Outcome:** ESCALATED at LLM proposal cap (8 proposals, 10 iterations),
616s. Best partial 8/11 criteria passing; still failing AC2 (-1.21),
AC9 (-67384), AC10 (-0.09).

**Progress vs baseline:** baseline CRASHED pre-generation
(F8.1 KeyError sigma). This time: sigma contract + deterministic default
worked - the flight survived preflight, drafted 11 criteria (ALL bound to
real pack checks - zero hallucinated names), generated a workbook, and
ran the full convergence loop. Deterministic recalibration + proposal 2
fixed six criteria in three iterations.

**Observations:**
- GUARD WORKING (positive): the coverage guard used its PROCEED-WITH-NOTES
  path in production for the first time ("proceeding with noted
  vocabulary/qualifier gaps"); flight continued with notes logged.
- The loop is effective when the system is feasible: discount ladder
  (AC4-7), monotonicity (AC3), tier share shift (AC2), deal size decline
  (AC8) all reached their bands at some point.
- The killer is **AC9 `avg_price_by_tier max_avg_realized_usd=15000`** -
  a jointly near-infeasible target: SMB plan attainment is raked to 105%
  (AC1), entry revenue share must stay 25->40% (AC2), so avg entry
  realized price is pinned by plan economics (entry_revenue / entry_count),
  NOT by price knobs. Proof: proposal 8 cut median_usd to $1,500 and
  realized price still read $28k next iteration - quota raking scales
  prices back up to meet plan totals. The proposer spent 6 of 8 proposals
  and huge score swings ($177k worst margin) chasing unreachable math.
- Scoring pathology: AC9's dollar-denominated margin dominates the
  lexicographic score; criterion-count stalled at 8/11 from iter 5 while
  the numeric axis kept wobbling, so neither stall detection nor
  since_improve fired before the cap.
- AC10 blended_margin_trend orbited its band edge (-1.4 to -2.4pp vs
  [-4,-2]): the proposer's learned margin transfer model repeatedly
  mispredicted by ~0.5-1pp.
- Two REGRESSION REVERT events fired correctly and preserved best partial.

**Failures & classification (logged only - no fixes during certification):**
- F13.1 GUARD-WORKING (positive evidence): proceed-with-notes graduation
  exercised on a real vocab/qualifier gap; naming contract held (11/11
  real check ids).
- F13.2 BUG-FEASIBILITY-DETECTION (family: impossible-math): jointly
  infeasible criterion systems (price cap under plan-raking with pinned
  share/attainment) are not detected - neither at Gate 1 nor mid-loop -
  so the budget burns on unreachable math instead of escalating early as
  structural. Scenario_01's structural detector caught absent UNITS;
  this shape (cap vs raking economics) escapes it.
- F13.3 GAP-AUTOMATION (family: transfer-model): blended-margin predicted
  effect inaccurate; repeated band-edge misses.
- F13.4 OBSERVATION (family: scoring): mixed-unit margins (dollars vs pp)
  let one criterion dominate the score and mask criterion-set stall;
  candidate post-certification fixes: per-criterion margin normalization
  or escalate when the PASSING SET is stale N iterations even if scores
  wobble.

**Actions:** logged only. NO code changes (certification run in progress).

---

### Batch 4 - scenario_04 (whitespace under-covered after capacity added)

**Outcome:** ESCALATED at preflight calibration, 385s, zero iterations.
Two corrective simulator drafts both missing the same block; escalation
on "no improvement across corrective drafts".

**Progress vs baseline:** previously ESCALATED at the coverage guard
(F9.1 qualifier pedantry + F9.2 portfolio-composition vocab hole +
hallucinated check suggestion). This time the guard PROCEEDED WITH NOTES -
the portfolio-composition claim was noted as a vocabulary gap and the
other five claims were accepted. Guard is no longer this story's bottleneck.

**Observations:**
- Deterministic synthesis worked for two other needs: ownership block
  (unowned curve 38%, churn 8%/qtr for AC4) and heterogeneous territory
  attainment (laggards 0.7 for AC2).
- The killer: AC3 `headcount_growth_placement` requires the `capacity`
  config block; the drafter never drafted one, and the corrective re-draft
  loop could not fix it in two attempts.
- The irony: the autopilot CAN synthesize capacity blocks - scenario_01's
  log shows "capacity: synthesized capacity block (6 reps/quarter plan)"
  when effective_capacity criteria need it. But the headcount_growth_placement
  requirement path only emits a HARD finding demanding a re-draft instead
  of triggering the existing deterministic synthesis.
- The corrective-findings message ("criterion ... but the required config
  block is missing (capacity)") names the block but gives the drafter no
  SHAPE to copy, and both redrafts came back without it.

**Failures & classification (logged only - no fixes during certification):**
- F14.1 BUG-PREFLIGHT (family: block-synthesis coverage): required-block
  handling is inconsistent across checks - some requirements trigger
  deterministic synthesis (capacity-for-effective_capacity,
  pricing_response), others only a HARD redraft demand
  (capacity-for-headcount_growth_placement); when the drafter has a blind
  spot, the redraft loop dead-ends. Candidate fixes (post-certification):
  route all known required blocks through deterministic synthesis, or
  embed a concrete block skeleton in the corrective findings message.

**Actions:** logged only. NO code changes (certification run in progress).

---

### Batch 5 - scenario_05 (forecast miss via slippage into next quarter)

**Outcome:** **LANDED UNASSISTED** - converged in 2 iterations, 338s,
6/6 criteria passing on measured data. Gate 2 delivered.

**Progress vs baseline:** previously ESCALATED at the coverage guard
(F10.1 legitimate direction-inversion save + F10.2 commit stage-composition
vocab holes). This flight is the certification run's first landing.

**Observations:**
- The drafter got the forecast direction RIGHT on the first draft this
  time: `forecast_vs_actual target_pct=106` (commit above actual = miss).
  The F10.1 inversion did not recur - and had it, the graduated guard's
  bounded redraft now handles exactly that parametric shape.
- Guard again used proceed-with-notes for the commit stage-composition
  claims (F10.2 vocab holes remain roadmap items).
- **Draft-repair safety net worked**: the first simulator draft carried
  `quota.attainment['Enterprise']` as a LIST where a scalar belongs -
  the same shape-deviation class that crashed scenario_02 (F12.1). Here
  the deviation hit a path validate_simulator_doc type-checks properly
  (raises ConfigError), so deterministic repair ran, failed, and the
  corrective re-draft recovered without human help. scenario_02 vs
  scenario_05 is now a clean contrast pair pinning exactly what F12.1
  hardening needs (ConfigError everywhere instead of raw AttributeError).
- Deterministic recalibration was the workhorse: synthesized the forecast
  block (commit running 106% of actual), solved the slippage path
  (+17pp vs >=5pp), and fixed its own staleness overshoot between
  iterations (68.3% predicted -> shortened durations to [1,2] days +
  reshaped share_open curve -> 33.5% actual vs <=40% band).
- Criteria quality good across the board: plan/forecast/coverage/aging/
  slippage/volume all real checks with sane params.

**Failures & classification:** none. Positive evidence:
- GUARD-WORKING (notes path, second production use)
- REPAIR-WORKING (F19/F17 corrective re-draft path; direct counterexample
  to F12.1's crash mode)

**Actions:** logged only. NO code changes (certification run in progress).

---

### Batch 6 - scenario_06 (Ent missed / MM beat via quota-vs-potential mismatch)

**Outcome:** ESCALATED at iteration cap (10), 376s, best partial 4/5.
The one persistent failure: AC4 Enterprise quota-vs-potential stuck at
~39-41% against a 120% target.

**Progress vs baseline:** baseline LANDED here after the D1/D2 fixes and
a verification re-fly. This is the first certification REGRESSION - see
root cause; the difference is drafter behavior, not lost fixes.

**Observations:**
- The drafter wrote AC4/AC5 WITHOUT `unit` params: two quota_vs_potential
  criteria on dimension=segment with DIFFERENT targets (Ent 120%, MM 40%),
  neither scoped to its segment. The baseline flight's criteria carried
  explicit `unit` params - that is the entire delta between landing and
  escalating.
- The closed-form remedy then mis-solved: autopilot log shows it scaled
  ALL segment plans to 120% (AC4's target), then ALL segment plans x0.33
  to 40% (AC5's target) - last criterion wins, both segments end at 40%,
  AC4 is permanently broken. Remedy keys on dimension, ignores unit
  scoping when absent, emits no warning.
- From iteration 2 on, the state was unsolvable by knob turns: raking
  pins revenue attainment to plan (AC1/AC3 pass), while plan/potential
  ratios are plan-of-record. The proposer nevertheless proposed
  `quota.attainment_by_segment.*` turns three times with confidently
  wrong predicted effects ("raises Enterprise quota-vs-potential toward
  120%" - attainment does not enter that ratio), plus two EMPTY proposals
  (iterations 3-4 burned no-ops). Regression reverts correctly preserved
  best-partial throughout; seed bump draw-noise recovery also fired once.
- Display bug: from iteration 2 the verdict table shows AC4's Actual as
  "40% (Mid-Market)" while AC4's criterion name/unit is Enterprise -
  mislabeled unit in the check's actual-value reporting.

**Failures & classification (logged only - no fixes during certification):**
- F15.1 BUG-AUTOPILOT (family: multi-target solve interference): the
  quota_vs_potential remedy applies one target ratio to EVERY unit of the
  named dimension when criteria lack `unit` scoping; multiple same-
  dimension targets clobber each other last-writer-wins, silently
  converting a solvable config into an unsolvable one. Candidate fixes:
  require/warn-on-missing unit at Gate 1; solve per-unit jointly; never
  overwrite a unit a previous criterion already pinned.
- F15.2 BUG-GUARD-CALIBRATION (family: cross-criterion consistency):
  two conflicting targets on the same check+dimension without disjoint
  unit scopes passed Gate 1 silently. Same family as F11.2 - criteria-vs-
  schema linting would catch it.
- F15.3 GAP-KNOWLEDGE (family: proposer transfer model): proposer lacks
  the blocked-path fact that attainment knobs cannot move plan/potential
  ratios (G14 family); wrong predictions + empty proposals burned ~half
  the budget.
- F15.4 INFRA-DISPLAY (minor): quota_vs_potential verdict line reports
  the wrong unit's actual value when multiple units exist.

**Actions:** logged only. NO code changes (certification run in progress).

---

### Batch 7 - scenario_07 (bookings -3%, pipeline creation +12%, low-ICP mix)

**Outcome:** ESCALATED by OSCILLATION guard after 6 stale iterations
(D3 fix working as designed), 513s, best partial 2/4. Still failing:
AC1 creation trend, AC3 deal-size trend.

**Progress vs baseline:** scenario_07 was never flown in Pass 1 (one of
the 18 cancelled). New measurement.

**Observations:**
- SIGN-CONVENTION TRAP: the drafter expressed the story's "+12% pipeline
  creation growth" as `creation_volume_trend target_decline_pct: -12`.
  Iteration 1 PASSED this criterion (+11.9% actual growth) - so the
  drafter's encoding was semantically right. But the KNOB PROPOSER then
  misread the parameter, flipped `volume_multipliers` downward to
  "produce the decline", and DESTROYED a passing criterion (-9% actual
  vs wanted +12% growth). It spent the rest of the flight fighting its
  own turn. The matrix vocab documents checks for the coverage guard,
  but sign conventions never reach the knob_proposer context.
- COUPLED-KNOB TRADEOFF: `volume_multipliers` simultaneously moves
  creation volume (AC1), avg won deal size via raking (AC3), and ICP
  share denominators (AC2). Proposals optimized one criterion at a time
  and traded the others away - the escalation reason literally reads
  "proposals keep trading criteria against each other". No joint
  transfer model exists for shared knob axes.
- WHALE NOISE: avg won deal size whipped between +45% and +108% on small
  won-count quarters (outlier draws dominate means); huge margin variance
  fed the oscillation.
- Positives: oscillation/stall detection escalated EARLY (cap 10 not
  reached); regression reverts fired 5 times and preserved best partial;
  icp_creation_shift was solved and held.

**Failures & classification (logged only - no fixes during certification):**
- F16.1 GAP-KNOWLEDGE (family: param semantics): check-parameter sign
  conventions (e.g. target_decline_pct) are documented nowhere the knob
  proposer can see; a passing criterion was misread and broken by its own
  autopilot. Candidate fix: inject per-check vocab/signature docs from
  the claim matrix into knob_proposal prompts.
- F16.2 ARCHITECTURE-GAP (family: coupled-knob planning): proposals lack
  a joint transfer model across criteria sharing a knob axis; single-
  criterion optimization guarantees trade-off oscillation on coupled
  systems.
- F16.3 OBSERVATION (family: estimator noise): outlier-whale dominance of
  small-sample means makes deal-size margins high-variance; candidate:
  median-based or trimmed variants.

**Actions:** logged only. NO code changes (certification run in progress).

---

### Batch 8 - scenario_08 (COGS up, discounts concentrated in high-margin products)

**Outcome:** ESCALATED at LLM proposal cap (8), 586s, final 4/6, best
partial 5/6 (reached but lost to criterion trading). Persistent: AC3
`elasticity_differential` (-1.3pp actual vs >= +3pp - INVERTED direction:
high-potential wr change negative while low-potential positive) and AC6
`tier_share_shift` entry start-point (28.1% vs ~20%).

**Progress vs baseline:** never flown in Pass 1. New measurement.

**Observations:**
- The deterministic layer again solved the hard-sounding parts and HELD
  them across all 10 iterations: blended margin erosion (-2.3pp vs
  -3+/-1), discount monotonicity, discount-margin link (+9.5pp gap),
  plan attainment pinned at 100%.
- The two failures live on INTERACTING pricing-mix axes: elasticity
  differential is driven by `pricing_response.elasticity/potential_mitigation`
  while tier mix is driven by catalog shares x price multipliers - and
  both move realized prices, so single-axis proposals traded one against
  the other across iterations (best oscillated 5/6 <-> 4/6; five
  regression reverts).
- AC3 ended INVERTED (-1.3pp vs wanted +3pp): proposals nudged elasticity
  knobs without ever flipping the response tilt between potential
  cohorts; the check's wr-delta semantics (per potential cohort) are not
  in the proposer's knowledge.
- Same meta-pattern as batch 7: near-miss oscillation around the landing
  boundary with coupled knobs.

**Failures & classification (logged only - no fixes during certification):**
- F17.1 GAP-KNOWLEDGE (family: coupled-knob planning, extends F16.2):
  elasticity/potential-response semantics of `pricing_response` absent
  from proposer context; differential-direction criteria cannot be steered
  by a proposer that does not know which knob flips the tilt.
- F17.2 OBSERVATION (family: search dynamics): lexicographic scoring +
  regression revert preserves best COUNT but the identity of passing
  criteria keeps rotating; no mechanism accumulates satisfied constraints
  monotonically (no constraint-freezing once a criterion enters band).

**Actions:** logged only. NO code changes (certification run in progress).

---

### Batch 9 - scenario_09 (expansion down where AE ownership changed recently)

**Outcome:** **LANDED UNASSISTED** - converged in 7 iterations, 391s,
2/2 criteria passing. Gate 2 delivered. Second certification landing.

**Progress vs baseline:** never flown in Pass 1 (criteria count 1 in the
UAT manifest). New measurement.

**Observations:**
- Drafter criteria were excellent and minimal: `core_vs_headline_growth`
  (headline >= -5%, core <= -12%) + `post_change_revenue_decline`
  (gap >= 10pp) - exactly the two checks the story needs, correct
  directions, sane bands.
- Iteration 1: AC1 passed immediately, AC2 read INVERTED (+30.8% on
  changed-owner accounts vs -0.8% stable). The autopilot then executed a
  sophisticated composite synthesis: sized the outlier_deals block
  (share curve x6.625 + per-quarter medians + deal-count floor) to force
  the core-declines/headline-grows split, which re-shaped ownership-cohort
  revenue trajectories until AC2 crossed into band with a huge margin
  (+47.79).
- The loop needed no LLM proposals at all after early iterations -
  deterministic recalibration carried it (consistent with the batch-1
  observation that the deterministic layer is the workhorse).

**Failures & classification:** none. Positive evidence: GUARD-WORKING,
AUTOPILOT-WORKING (block synthesis composed from multiple knobs toward a
two-criterion joint target).

**Actions:** logged only. NO code changes (certification run in progress).

---

### Batch 10 - scenario_10 (capacity +10% but attainment -6pts, ramp placement)

**Outcome:** ESCALATED at convergence - structural failures AC3/AC4/AC5,
389s. The purest specimen yet of the scoping/feasibility family.

**Progress vs baseline:** never flown in Pass 1. New measurement.

**Observations:**
- PSEUDO-UNITS FROM STORY NOUNS: the drafter invented capacity plan units
  called 'headline' and 'effective' - story PROSE words ("headline
  headcount", "effective productive capacity") turned into coordinate
  names. The synthesized capacity block has real territory units; AC3/AC4
  reference units that can never exist.
- PHANTOM SOLVE RECURRENCE (F11.1 exactly): autopilot logged "AC4: solved
  ramping counts for effective capacity ~92% (unit 'effective')" for the
  nonexistent unit - success claimed, validator reports unit absent.
- CONFLICTING UNSCOPED TARGETS PASSED GATE 1 (F15.2 exactly): AC1 wants
  company-wide plan attainment 94%+/-2, AC2 wants 100%+/-2 on the SAME
  check/dimension/unit - non-overlapping bands, provably jointly
  unsatisfiable, accepted without comment.
- Repair path worked again: first draft had quota.by_segment['_all_'] /
  ['All'] (invalid segment labels) -> ConfigError -> corrective re-draft
  recovered. Second F12.1-contrast data point.
- Minor diagnostic bug: the PF0 message printed "(known: [])" although
  accounts.segments was populated - misleading error text sent to the
  corrective re-draft.

**Failures & classification (logged only - no fixes during certification):**
- F18.1 RECURRENCE of F11.1 (phantom solve): effective_capacity solver
  reports success for absent units. Now observed twice; the fix must be
  in the solver's precondition, not per-check.
- F18.2 RECURRENCE of F15.2 (conflicting targets through Gate 1): now
  observed twice with provably-unsatisfiable bands. Same root:
  no cross-criterion consistency lint.
- F18.3 BUG-GUARD-CALIBRATION (family: vocabulary grounding): drafter
  mints pseudo-coordinates from narrative language ('headline',
  'effective'); nothing at Gate 1 grounds criterion coordinates against
  the legal unit space of the target dimension - which entity schemas
  define but nothing enforces.
- F18.4 INFRA-DIAGNOSTIC (minor): PF0 known-segments message renders an
  empty list; corrective drafts receive wrong information.

**Actions:** logged only. NO code changes (certification run in progress).

---

## MID-CERT SYNTHESIS (after 10 flights - introspection pause)

### Scoreboard

| Metric | Certification (n=10) | Baseline-as-built |
|---|---|---|
| Flown | 10 | 7 |
| Landed unassisted | 2 (scenario_05, 09) | 1 of 7 (14.3%) |
| Escalated | 7 | 5 of 7 |
| Crashed | 1 (scenario_02) | 1 of 7 |
| Landing rate | 20.0% | 14.3% |

**Death-layer shift:** baseline non-landings died at the coverage guard
5-of-6. Certification non-landings: ZERO guard deaths. Deaths now sit at:
simulator draft crash 1 (F12.1), preflight calibration 1 (F14.1),
convergence loop 5. The M6 guard thesis is CONFIRMED; the bottleneck has
moved downstream exactly as designed.

### The one common denominator (now unambiguous)

**Coordinate scoping + feasibility are unvalidated at Gate 1.** Counting
recurrences: phantom solves (F11.1+F18.1), cross-block dimension
mismatch (F11.2), remedy unit-clobber (F15.1), conflicting targets
(F15.2+F18.2), pseudo-units from story nouns (F18.3), economic
infeasibility chased to cap (F13.2). Eight failures across five flights,
one family: *criteria reference coordinates/targets that nothing checks
against the data model's actual geometry.* The entity schemas describe
that geometry completely and enforce nothing at flight time.

Secondary families: proposer knowledge gaps (sign conventions, blocked
paths, pricing_response semantics - F16.1/F17.1/F15.3); solver-framework
fragmentation (F14.1/F11.3); search dynamics without constraint freezing
or normalized margins (F13.4/F17.2).

### What works (positive evidence)

- Guard graduation: notes path x4, bounded redrafts, zero false kills.
- Corrective-redraft repair net: saved invalid drafts 3x (scenario_05
  list-scalar, scenario_10 bad segment labels, plus scenario_05's own
  redraft); crashes only where errors escape ConfigError typing.
- Deterministic layer is the workhorse in every single flight;
  both landings were carried by autopilot synthesis with minimal LLM
  proposals.
- Oscillation guard fired EARLY (batch 7); regression reverts protected
  best-partial in every escalated flight.

### Candidate P5 package (post-certification, priority order)

1. Gate-1 criteria lint against entity schemas + plan-unit registry +
   cross-criterion consistency (kills the scoping family at the door).
2. Solver-framework unification: shared unit-target ledger, uniform
   required-block synthesis, no phantom solves (solver precondition).
3. Feasibility pre-check: pinned-constraint vs free-knob solvability
   sketch before entering the loop; impossible -> early structural
   escalation with named contradiction.
4. Complete input hardening: ConfigError on every type-shape deviation.
5. Proposer knowledge injection: check signatures/sign conventions,
   blocked paths, transfer functions via pack SemanticPrompts.
6. Search dynamics: margin normalization, constraint freezing once a
   criterion enters band, stale-passing-set escalation.
