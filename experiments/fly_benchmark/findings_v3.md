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

