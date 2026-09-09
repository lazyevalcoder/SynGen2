# Fly Benchmark Findings v3 — Fresh-Cohort Verification (scenarios 11–15)

> **Purpose:** P5's flight-control envelope was designed from the failure
> taxonomy of scenarios 01–10 (see `findings_v2.md`). Before resuming the
> full certification sweep, we fly scenarios 11–15 — never seen during
> design — to verify the fixes generalize beyond their derivation set.
>
> **Code line:** `6d91bdc` (P5 complete). Protocol unchanged: one scenario
> per batch, diagnosis logged before the next flight, no mid-run fixes.

## Scoreboard (this file)

| Scenario | Outcome | Iterations | Elapsed | Escalation reason |
|---|---|---|---|---|
| 11 | **LANDED** | 1 | 670s | - |
| 12 | escalated | 8 | - | stale passing set |
| 13 | **LANDED** | 1 | 585s | - |
| 14 | **LANDED** | 1 | 576s | - |
| 15 | escalated | 0 | - | criteria_geometry |
| 16 | escalated | 0 | - | generation failed on initial config ('segments') |
| 17 | escalated | 7 | - | oscillating (no net score improvement) |
| 18 | escalated | 0 | - | criteria_consistency |
| 19 | escalated | 2 | - | structural failure (AC3 outside data model) |
| 20 | escalated | 9 | - | oscillating (no net score improvement) |

---

## Batch 20 (2026-08-26) — scenario_20 · ESCALATED ❌ (oscillation guard, 9 iters)

The most compound story yet — 8 criteria: blended margin +2pp, company
miss ~95%, Enterprise below target, SMB mix → higher-margin core, pricing
realization 87→92, elasticity driver ≥5pp, discount guardrails, opposite
directions. Peaked at 5/8 passing, oscillated, guard cut at 9.

### Failures (three recurrences, one new)

- **F19.9 knob-blindness, strongest instance yet**: AC6
  (`realization_elasticity_driver`) printed **+0.6pp differential in all
  9 iterations — never moved once**, because the config has no
  territory-potential dimension for the elasticity signal to construct
  (same missing surface as scenario_16). AC8 headline also pinned at
  +0.0% (exact scenario_17 signature). Two metrics in one flight are
  knob-inert.
- **F19.2 margin-model error recurs**: autopilot predicted "+0.0pp
  blended margin change" after scaling spread ×0.02; actual deltas swung
  +3.8 → -0.5 → +2.5 across iterations. The margin predictor is not
  trustworthy for target ±1pp bands (third recurrence: s12, s20).
- **F19.4 best-partial amnesia recurs**: 5-passing states (iters 3, 6, 7,
  8) reverted to 4- or worse states via the "reverting to best partial"
  path — the 5-passing state was never the restored baseline.
- **F19.11 (new, search-quality): unstable target tracking under wide
  overshoot.** AC5 (realization 87→92 ±2) oscillated 84→89.5→92→85→91.5→
  83.4→81→95.2 across proposals — the proposer overshoots both ends of
  the band and never converges onto it. Combined with the revert logic
  discarding its own best hits, the search jitters instead of homing.

### Positives
- Oscillation guard fired correctly (3rd live fire) with precise
  failing set + margins.
- Autopilot still sized outlier_deals + deal-count floor and ran the
  AC5 base-shift + AC1 spread paths without crashing.
- The compound claim structure (8 criteria over 3 story clusters) was
  decomposed and Gate-1-signed cleanly — decomposition quality held even
  on the hardest story so far.

---

## Fresh-Cohort Summary — Scenarios 16–20 (code line 6d91bdc)

| Metric | 11–15 | 16–20 | 11–20 combined | Baseline-as-built |
|---|---|---|---|---|
| Landed | 3/5 (60%) | **0/5 (0%)** | 3/10 (30%) | 1/7 (14.3%) |
| Escalated | 2 | 5 | 7 | 5 |
| Crashed | 0 | 0 | 0 | 0 |
| Guard deaths (correct) | 1 | 5 | 6 | 6/6 non-landings |

### The 16–20 cohort is a different animal
Three structural/vocabulary deaths (16 crash-class via F19.7+F19.8,
18 F19.6 consistency, 19 F19.10 missing surface) and two search-quality
deaths (17, 20 oscillation). All five deaths were **cheap and
precise** — Gate-1 or early-loop, named criteria, actionable messages.
No flight died in an unhandled exception; no phantom success was claimed.

### Failure-family tally across v3 (11–20)
| Family | Name | Flights |
|---|---|---|
| F19.6 | cohort/subset vocabulary gap (geometry-fatal) | 15, 18 |
| F19.9 | proposer knob-blindness (metric inert to knobs) | 17, 20 |
| F19.2 | calibration↔engine model drift (margin, tier-share) | 12, 20 |
| F19.4 | best-partial revert discards margin progress | 12, 17, 20 |
| F19.10 | check needs data-model surface generator lacks | 19, (20-AC6) |
| F19.11 | unstable band tracking under overshoot | 20 |
| F19.7 | crash-class: engine hard-key on absent config key | 16 |
| F19.8 | guard-policy: unknown checks passed Gate 1 | 16 |
| F19.5 | one-sided band semantics (vocabulary) | 13, 14 |
| F19.1 | directional endpoint semantics (vocabulary) | 11 |

### Verdict
- P5's defenses held **everywhere**: zero unhandled crashes, every new
  guard family fired live at least once, all deaths are honest,
  precisely-attributed, and cheap. Generalization confirmed.
- The remaining killers are **not** the P5 target families — they are
  (a) vocabulary gaps masquerading as gate failures (F19.6/F19.8), (b)
  missing generator surfaces for declared checks (F19.10), (c) search
  dynamics (F19.4/F19.9/F19.11), (d) calibration-model fidelity
  (F19.2). This is the second death-layer shift — from intake/guard to
  engine-surface + search quality.

### Next-wave priority (supersedes earlier list)
1. **Vocabulary & surfaces (biggest lever)**: cohort expressions
   (F19.6), hiring-flow surface for headcount_growth_placement (F19.10),
   territory-potential dimension (F19.9-AC6/s16), and unknown-check ⇒
   gap escalation (F19.8). These four close 6 of 10 deaths.
2. **Best-partial revert keyed to margin quality** (F19.4) + band-homing
   guidance for overshooting proposer (F19.11).
3. **Margin predictor recalibration** (F19.2).
4. **Engine default for `accounts.segments`** when absent (F19.7).


---

## Batch 19 (2026-08-26) — scenario_19 · ESCALATED ❌ (structural failure, 2 iters)

Headcount/capacity story (revenue missed by 4%; effective capacity ~87%
due to ramping AEs; ramping share exceeded the plan's assumption).

### Outcome
Escalated by the structural-failure guard after 2 iterations: `['AC3']`
"reference something outside the data model even after deterministic
re-calibration". Final config shows `capacity: {}` and `planning: {}`;
AC3 printed "no headcount additions, headcount unchanged FY26-Q1→Q4".

### Failure — F19.10 (capacity synthesis is growth-blind: level ≠ flow)
`headcount_growth_placement` measures the share of headcount **additions**
that were ramping reps. The only synthesis path for the capacity block
(preflight.py:1244-56) produces a flat `headcount_plan: [6]*n_q` — a
*level* with no inter-quarter growth, hence zero additions, hence the
criterion is structurally unlandable no matter the knob turns. And in
this flight the final config's `capacity` came out `{}` entirely,
meaning the synthesized block did not survive the corrective re-draft
that replaces simulator.json after critic B (synthesis ran pre-convergence,
then a re-draft reserialized a fresh config without it — the "even after
deterministic re-calibration" retry also failed to restore it). Two
distinct defects: (a) no hiring-flow surface exists in the config schema
for the check to land on; (b) capacity synthesis is not re-applied after
config re-drafts.
- Effective capacity (AC2, a *level* target) PASSED at 86.7% — confirming
  the block synthesis works for level checks; the gap is specifically the
  growth/additions surface.

### Positives
- Structural-failure guard gave a precise, cheap death (2 iterations)
  naming AC3 and the margin; no phantom solve was ever claimed.
- Auditor's notes correctly steered the drafter toward
  `headcount_growth_placement` — the right check, let down by the engine
  surface, not by intent.


---

## Batch 18 (2026-08-26) — scenario_18 · ESCALATED ❌ (criteria_consistency, Gate 1)

Quota-attainment story (top-quartile over-attainment, territory quota vs
potential spread).

### Outcome
**First live fire of the WP2 consistency lint AND its escalate path.**
`AC3 quota_vs_potential 120±10` vs `AC6 quota_vs_potential 70±15` on the
same coordinate `{'dimension': 'territory', unit: None}` — non-overlapping
bands → provably jointly unsatisfiable → one corrective re-draft (still
conflicting) → escalated. Died at Gate 1 in two rounds: the cheapest
possible death for an impossible contract, precisely the F15.2/F18.2
class P5 targeted.

### Diagnosis

- **The lint is correct**: both criteria claim the ENTIRE territory
  dimension is simultaneously 120% and 70% of potential. Genuinely
  unsatisfiable.
- **F19.6 recurrence at root**: the story means "top territories ~120%,
  small ones ~70%" — subset claims. With no cohort vocabulary the
  drafter could only emit whole-dimension claims, which necessarily
  contradict. The re-draft couldn't resolve it because the vocabulary
  is the blocker, not the drafting.
- Improvement: the consistency lint should drive a corrective brief
  suggesting the *expressive* resolution (scope to distinct units, or
  collapse into a single `min_spread_pp` criterion — the F19.6 cohort
  fix would supply real subset semantics). Escalation remains the right
  terminal behavior for "still unsatisfiable after one re-draft".

### Positives
- Guard policy held exactly to design: bounded single re-draft, then
  honest escalation naming the conflicting coordinate pair. No burned
  convergence budget.
- Auditor's "consistently" qualifier note was substantive — flagged that
  over-attainment needs temporal consistency, not a point-in-time pin.


---

## Batch 17 (2026-08-26) — scenario_17 · ESCALATED ❌ (oscillation guard, 7 iters)

Whale-deal story (headline revenue carried by few huge deals while core
ex-whale volume declined; end-of-quarter close clustering; region beat
plan; top-3 concentration).

### Outcome
Escalated by the WP8 **oscillation** guard (2nd live fire of the
escalation family): "no net score improvement for 6 iterations (proposals
keep trading criteria against each other); still failing ['AC2','AC3',
'AC4']". Best-observed state was iter 1–2 at 3/5 passing; guard cut it
off honestly instead of burning the full budget.

### Failures

- **F19.9 (proposer knob-blindness): headline growth is insensitive to
  every knob the proposer tried.** AC2 wants headline (total) Q1→Q4
  growth ≥10%; across seven proposals — attainment raised 1.04→1.12,
  outlier share 0.02→0.16, multiplier 13→16 — headline printed **+0.0% in
  every single iteration** while the ex-whale core moved freely (-81 → -54
  → +1.3%). The proposer's model treats level-shifts (attainment,
  share-by-quarter) as growth-shifts; nothing actually moved the endpoint
  differential. AC4 is a second data point: `close_clustering`
  0.3→0.55/0.62 moved the EOQ-vs-mid gap only 5.4→6.0pp against a +25pp
  target — a weak-effect knob. The search had no effective lever on two of
  its three failures, guaranteeing the oscillation the guard detected.
- **F19.4 (best-partial amnesia) recurs with concrete numbers**: best
  states (3 passing, AC3 +22.23) were discarded for 2-passing states with
  AC3 at -20.48; revert restores the *worst* partial every time.

### Positives
- Autopilot sized the outlier_deals block once deterministically.
- Oscillation guard's message names mechanism, failing criteria, and
  worst margins — exactly the actionable-death design.
- The whale↔core tradeoff is genuinely adversarial (raising whale share
  helps AC2/AC3 but violates AC5's core decline bound); the search
  correctly identified it repeatedly, it just lacked a joint lever.


---

## Batch 16 (2026-08-26) — scenario_16 · ESCALATED ❌ (generation crash on initial config)

Territory price-elasticity story (high-potential territories held
conversion through a price increase; low-potential deteriorated; SMB
bookings down ~5%, concentrated by potential tier).

### Outcome
Generation crashed at iteration 1 with `KeyError: 'segments'`. Error-path
telemetry worked exactly as designed (F8.2/F5.3): caught, logged,
escalated with the exception name — **not an unhandled crash** — but it
is still a crash-class death.

### Failures

- **F19.7 (F12.1-family recurrence, unhardened spot): engine
  hard-requires `accounts.segments`.** The drafter legitimately omitted
  segments (story never mentions them; config used
  regions/territories/industries — all valid shapes). Every consumer
  reads `accounts.get("segments", {})` defensively EXCEPT
  `build_accounts` (generator/engine.py:73), which does bare
  `spec["segments"]`. WP5's shape guard validates dict-shape *if
  present* but absence sails through validation into the KeyError.
  Fix shape: default `{"All": 1.0}` when absent (mirroring
  preflight.py:501) + a regression test with a segment-less config.
- **F19.8 (guard-policy hole): unknown checks passed Gate 1 as display
  annotations.** The final criteria contain two hallucinated checks
  (`post_change_bookings_decline`, `bookings_deterioration_concentration`)
  rendered `[UNKNOWN CHECK]` in the criteria table — yet signed off.
  M6 doctrine says the auditor must name an EXISTING check or classify
  VOCAB-GAP; here non-existent names flowed to convergence where they
  would have failed at evaluation (had generation survived). Unknown
  check ⇒ coverage gap ⇒ bounded redraft → escalate, same as any
  vocabulary hole.

### Positives
- Critic B's config blocks were exceptional this flight — it correctly
  identified that the simulator has NO territory-potential dimension at
  all, so AC1's elasticity differential "can pass or fail on noise
  rather than proving the story's mechanism," and that AC2/AC3's overall
  decline and its concentration are decoupled in the generator. That is
  a real structural read of the data model, not pattern-matching.


---

## Batch 15 (2026-08-26) — scenario_15 · ESCALATED ❌ (criteria_geometry, pre-convergence)

Territory quota-design story (quotas 20–25% above addressable market on
large territories, modest quotas + whitespace on small ones). First-ever
flight of this scenario (v1 baseline flew 06,01–05,17 — **no regression**).

### Outcome
Died at the WP3 geometry cross-lint, pre-convergence, with criteria.json
persisted and legal units named in the message:
- AC3 `quota_vs_potential unit="top_potential_territories"` — not in the
  data model.
- AC4 `unit="small_territories"` — not in the data model.

### Diagnosis

- **The kill is correct-by-design.** These are drafter-minted *cohort
  pseudo-units* — exactly the F18.3 class P5 was built to stop. Under
  the old line they would have sailed into convergence and produced a
  phantom solve or vacuous pass (F11.1). An honest death beats a fake
  landing.
- **But the root cause is a vocabulary gap wearing a geometry costume**
  (**F19.6**): the story legitimately needs *subset/cohort expressions*
  ("the largest territories", "smaller territories") and the pack has no
  way to say them — no top-N-by-potential parameter, no size-bucket
  cohorts. The drafter did the only thing it could: invent units.
  Doctrine says vocabulary holes should route to the roadmap queue, not
  kill flights; here the hole is flight-fatal because geometry lint has
  no bounded re-draft path.
- **An expressible form existed**: AC5 already encodes the same substance
  as `min_spread_pp: 60` across the whole territory dimension — no units
  needed. A corrective re-draft prompted with the lint findings would
  plausibly have rewritten AC3/AC4 into spread/per-unit forms and saved
  the flight.

### Improvement candidates (for the fix wave, NOT mid-run)
1. **Bounded corrective re-draft on geometry findings** (mirror WP2's
   consistency-lint loop): feed lint output back to the drafter once
   before escalating. Cheapest high-yield fix.
2. Long-term: cohort parameter support in quota_vs_potential
   (`cohort: {by: potential, top_pct: N}` / size buckets) — real engine
   semantics for subset claims.

### Positives
- Gate placement validated: died BEFORE burning a proposal budget;
  persisted artifacts make post-mortem trivial; message names the legal
  coordinate space explicitly (F18.4's misleading-diagnostic lesson held).
- Critic A's pre-Gate-1 blocks were substantive (caught AC4's
  name/params/claim contradiction; grounded AC3's band against the
  story's 20–25% range).

---

## Fresh-Cohort Summary (scenarios 11–15, code line 6d91bdc)

| Metric | 01–10 (P4, pre-P5) | 11–15 (post-P5) | Baseline-as-built |
|---|---|---|---|
| Landed | 2/10 (20%) | **3/5 (60%)** | 1/7 (14.3%) |
| Escalated | 7 | 2 | 5 |
| Crashed | 1 (unhandled exception) | **0** | 0* |
| Guard deaths | 0 | 1 (correct) | 6/6 non-landings |

### Generalization verdict: P5 fixes hold on unseen ground ✅
- **Zero crashes** across the cohort (F12.1 class stayed dead; PF0 even
  self-healed one range violation live in scenario_11).
- **No recurrence of any F11.x–F18.x family** P5 targeted — including on
  machinery the fixes never saw (stage-history aging, activity blocks,
  forecast integrity).
- Every new defense fired live at least once: critic A/B (all five),
  PF0 hard-finding self-heal (s11), stale-set escalation (s12, first
  live fire), geometry lint (s15).
- **Remaining failure families are NEW and different in kind**: not
  intake/guard deaths but *model accuracy* (F19.2 calibration↔engine
  drift, F19.3 unreachable-without-joint-moves) and *search dynamics*
  (F19.4 best-partial amnesia) — i.e., deaths moved downstream of
  everything P5 addressed, consistent with the death-layer-shift
  pattern from v2.
- Vocabulary queue grew by three fidelity items (F19.1 directional
  endpoints, F19.5 one-sided bands, F19.6 cohort expressions) — all
  landed-anyway or logged-only, none flight-fatal except F19.6.

### Recommended next wave (priority order)
1. Geometry-lint corrective re-draft (fixes F19.6's fatality cheaply).
2. Best-partial revert keyed to failing-criterion margins (F19.4).
3. Tier-share/blended-margin calibration model recalibration (F19.2).
4. Joint price_mult×count-share remedy for tier-share targets (F19.3).


---

## Batch 14 (2026-08-26) — scenario_14 · LANDED ✅ (iteration 1, 5/5, 0 LLM proposals)

Forecast-integrity story (forecast ~9% hot, commits overshooting, cycle
time growth, widening slip). Forecast + quota blocks synthesized
deterministically; slippage path solved (+23pp vs ≥8pp).

### Observations
- Multi-round guard/critic interplay (3 gap-redrafts, critic A twice,
  critic B once) converged on signable criteria without escalation —
  bounded redraft budgets held.
- Minor fidelity compression: guard initially distinguished "commit
  overshoot" from "forecast overshoot" as distinct metrics, but the
  final AC1/AC2 both measure `forecast_vs_actual` at 109% — the
  commit-vs-actual distinction was absorbed rather than separately
  modeled. Landed within its signed contract; noted for the vocabulary
  queue alongside F19.1/F19.5 (metric-distinction expressiveness).
- AC4's margin (+62.8 vs ≥+8%) shows weak pinning — passes generously.
  Same one-sided-band family as F19.5, harmless here.


---

## Batch 13 (2026-08-26) — scenario_13 · LANDED ✅ (iteration 1, 4/4, 0 LLM proposals)

Sales-activity story (activity growth, misalignment toward low-potential
accounts) — exercised the **activity block**, never synthesized before
this cohort.

### Outcome & positives
- Autopilot synthesized an activity block with `potential_tilt -0.7`
  deterministically; convergence needed zero proposer calls.
- The **direction-correction loop worked end-to-end**: drafter twice
  produced wrong-direction trend params (`target_decline_pct=15` for a
  GROWTH claim); coverage-guard notes named the contradiction precisely
  ("a criterion measuring decline cannot fail if the claim is false") and
  corrective re-drafts fixed them before Gate 1. WP7 sign-convention
  knowledge demonstrably shaping drafts on fresh ground.
- Critic A/B each fired one bounded corrective re-draft.
- Compound claims decomposed honestly: conjunctive claims split so each
  half gets its own criterion (AC3 depends_on AC1).

### Candidate finding (non-fatal, logged only)
- **F19.5 (F19.1-family recurrence): `creation_volume_trend` band
  semantics are one-sided in practice.** Guard note reads the signed
  band as [-18%, +2%] (flat would pass — cannot prove growth), yet the
  engine passed actual +15% growth against target -10 ±8pp. Note-model
  and engine disagree on the band shape; either way the criterion pins
  only one side. Direction-pinning needs explicit two-sided or
  directional-band parameters. → vocabulary queue.


---

## Batch 12 (2026-08-26) — scenario_12 · ESCALATED ❌ (stale passing set, 3/5)

Pricing/mix story: SMB attainment 102% (passed immediately), blended
margin declined 2pts (AC2), entry-tier mix shift 25%→40% (AC3), discounts
rising (AC4), realized-vs-list slide (AC5).

### Outcome
Escalated after 8 iterations with AC2/AC3 never crossing. **The WP8
stale-set escalation fired live for the first time and its message is
exactly what we designed**: identical 3 criteria passing for 6 consecutive
iterations while ['AC2','AC3'] never crossed — remaining failures are not
reachable by knob turns. Honest early death instead of burning the full
budget against an unreachable target.

### Failures

- **F19.2 (calibration↔engine model error, tier revenue share):**
  Autopilot calibrated entry count-share "to solve ~25% revenue share"
  (Q1) but the engine measured 18.4% — the predictor materially
  underestimates the count→revenue share attenuation through
  price_mult/discounts. Same family as F13.3/F16.2 (model inaccuracy),
  new surface: tier mix.
- **F19.3 (unreachable target without joint moves):** AC3 wants 40%
  entry *revenue* share while `price_multiplier_by_tier.entry` = 0.4;
  revenue share ≈ count_share × price_mult makes that arithmetically
  near-impossible (~100% count share needed). The one proposal that
  attacked price_mult directly (iter 5, 0.4→0.25) regressed on other
  criteria and was reverted; no remedy composes count-share + price_mult
  jointly. Cross-lint (WP6) checks price caps vs raking floors but not
  tier-share reachability — candidate extension.
- **F19.4 (search dynamics, best-partial amnesia):** "Reverting to best
  partial state" repeatedly restored the SAME state (18.4% / -9.06pp)
  even though later iterations reached strictly better margins on the
  failing criteria (iter 4: AC3 27.4%, -7.63). Best-partial selection
  appears keyed to the passing set only, discarding margin-quality
  progress on failing criteria — the search throws away its own
  gradient information.

### Positives
- Bad-proposal rejection worked: shares summing to 1.164 rejected with
  a precise reason, zero corruption ("WARN bad proposal path skipped").
- Critic A blocked direction-contradiction criteria (+2 vs "declined")
  pre-Gate-1; redraft fixed them — sign-convention knowledge (WP7)
  visible in the guard notes' reasoning.
- Regression-revert discipline held throughout; escalation cause is
  actionable (names unreachable criteria + worst margins).


---

## Batch 11 (2026-08-26) — scenario_11 · LANDED ✅ (iteration 1, 8/8, 0 LLM proposals)

Fresh-cohort first flight: never seen during P5 design. The pipeline
coverage-decay story exercised stage-history aging, slippage trends, and
quota-relative coverage — machinery barely touched by scenarios 01–10.

### Outcome
Converged on iteration 1 with every knob solved deterministically
(`llm_proposals: 0`) — the Autopilot carried the entire convergence.

### Observations (P5 generalization evidence)
1. **Critic A engaged**: blocked 3 issues in drafted criteria → one
   corrective re-draft (WP9 verification point 1, firing on fresh material).
2. **Critic B engaged**: blocked 6 issues in config draft → one corrective
   re-draft (verification point 2), incl. a taxonomy ADVISE lint.
3. **PF0 input-hardening path worked end-to-end**: first calibration
   produced `share_open_by_quarter` = 0.9691 > 0.95 cap → ConfigError →
   PF0 HARD finding → bounded re-draft → second calibration clean
   (`[0.0879..0.6812]`, predicted stale 51%). This is the F12.1 crash
   class converted into a routine self-heal — on a scenario the fix was
   never designed against.
4. **Autopilot breadth on unseen ground**: slippage path solved (+22pp vs
   ≥10pp requirement), deal durations shortened when the staleness cap was
   unreachable at drafted cycle length ("the staleness cap was unreachable
   at the drafted cycle length"), per-quarter plan rescaling for all three
   coverage criteria.

### Candidate finding (non-fatal, logged only)
- **F19.1 (fidelity, landed-anyway): directional endpoint semantics.**
  Story asserts coverage *fell* 4.1x → 3.0x; dataset shows 4.61x → 4.67x
  (a rise). Both endpoint criteria use `coverage_ratio` floor semantics
  (≥4.1 / ≥3.0), which cannot express "declined TO 3.0" — a ceiling/band
  parameter class is missing. The graduated guard correctly routed the
  relational claim ("effective < reported") to notes (vocabulary gap),
  and Gate 1 signed the floors anyway. Flight is valid per its signed
  contract, but story-direction fidelity is weaker than the verdict
  table suggests. → vocabulary queue, not a flight failure.

