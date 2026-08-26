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

