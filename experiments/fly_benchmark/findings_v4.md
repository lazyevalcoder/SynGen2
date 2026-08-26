# Fly Benchmark Findings v4 — P6 Realizability Wave + Fresh-Cohort Verification

> **Purpose:** after the 11-20 cohort (findings_v3.md), the failure taxonomy
> collapsed onto ONE root event: *criteria accepted that the generator
> cannot truthfully construct, discovered only after committing to a
> flight*. P6 is the class-level fix for that class, built on branch
> `fix/realizability`. Verification runs on scenarios 21-25 — NEVER
> examined during any fix — because 11-20 are the derivation set and prove
> nothing about generality.
>
> **Code line:** branch `fix/realizability` (3 commits, 372 tests green).
> Protocol: one scenario per batch, diagnosis logged, no mid-run fixes.

## What P6 changed (each item = general rule, zero scenario conditionals)

### Part 1 — The realizability gate (accept only what the generator can build)
- **P1.1** unknown/hallucinated check names → hard finding at the
  consistency lint → bounded corrective redraft → escalate (F19.8).
  `criteria_lint.lint_criteria_internal` checks every criterion's check
  against the pack registry.
- **P1.2** engine defaults `accounts.segments` to `{"All": 1.0}` when a
  config legitimately omits segments (F19.7 crash class).
- **P1.3** geometry lint (cross_lint) gets ONE corrective criteria re-draft
  before escalating, with a hint to express subset claims as spread/scoped
  forms (F19.6 cohort pseudo-units).
- **P1.4** tier revenue-share targets above the arithmetic ceiling
  (count_share×price_mult with residual-other floor) flagged infeasible
  at the cross-lint (F19.3).

### Part 2 — The missing surfaces (additive engine capability)
- **P2.5** capacity synthesis produces a RISING headcount flow when
  `headcount_growth_placement` is required (level-only synthesis made the
  criterion structurally dead), plus a converge remedy that re-shapes
  additions into measured-strong units (runs before the structural check)
  (F19.10).
- **P2.6** `elasticity_differential` deterministic solver: sets the
  pricing_response price path + elasticity from the engine's own
  wr-multiplier model, with a deal-count floor so the per-cohort wr-change
  estimator is measurable (F19.9/AC6 knob-inert metric).
- **P2.7** `quota_vs_potential` cohort expressions: `cohort: {top_pct|bottom_pct}`
  restricts to the top/bottom N% of plan units by market potential —
  the expressible form for "the largest/smallest territories" (F19.6,
  resolves s15/s18's whole-dimension contradictions). Supported in the
  check, the signature registry, and the measured-plan remedy.

### Part 3 — The honesty net (calibration fidelity)
- **P3.8** `tests/test_calibration_agreement.py`: every closed-form solver
  (margin, tier-share, elasticity, coverage/levels) is run against a real
  workbook across 3 seeds — drift between a solver's prediction and the
  engine turns CI red. The sweep ITSELF caught and fixed the small-sample
  drift (deal-count floor) and quantified the margin metric's ~4pp seed-
  noise floor and tier share's ~5-8pp tail.
- Deal-count floor for noise-sensitive checks; margin noise-floor note in
  the consistency lint.

## Evidence of generality (so far)
- `git diff` of syngen/ + packs/: no scenario IDs, no segment names, no
  story nouns in any conditional — only in comments citing the motivating
  finding.
- The test for the flagged edit (removing a segment from a TEST quota
  helper) was config-invariant hygiene: quota segments must be a subset of
  the accounts segments the validator enforces.

## Verification plan (the real test)

1. **Fly 21-25 first** — the holdout the fixes never saw. Landing rate and
   death-quality there are the generality evidence. (11-20 are the
   derivation set; re-flying them would be circular.)
2. **Landing-set preservation** 05/09/11/13/14 — P6 must not regress what
   already landed (regression check, independent of derivation).
3. Report both to the user before any further change.

## Scoreboard (this file)

| Scenario | Outcome | Iterations | Escalation reason |
|---|---|---|---|
| 21 | structural-blocked (criteria landed) | 1 | **S21.1 [CONTRACT-BUG, not criteria]:** 4/4 criteria PASSED (AC1 630.9x, AC2 74.1%, AC3 71.0%, AC4 105.0% +5pp) — story genuinely landed — but the post-landing structure check FAILED on an *order-only* column mismatch: `sheet 'opportunities' column mismatch; missing=[] unexpected=[]`. Root cause: engine assigns `in_commit` (engine.py:570) then `is_outlier` (engine.py:931) → emitted order `[..., is_outlier, in_commit]`; contract `expected_sheets_for` (linter.py:233-239) appends `in_commit` then `is_outlier`. PRE-EXISTING (both predate P6; git master identical) and never exercised because structure check only runs after all criteria pass AND no prior landing enabled forecast+outlier_deals together. Fix is order-tolerance or reorder-in-one-place — parked, not fixing during 21-25. |
| 22 | escalated (stale set) | 7 | **S22.1 [REALIZABILITY-GAP, same class as F19.6]:** AC4 `quota_vs_potential` (dimension=territory, target 120%) returned `nan%` for EVERY unit on EVERY iteration → -inf margin, unbounded burn. Root cause (checks.py:757): accounts have NO territory column → dim falls back to `region`; quota plan units are segments `Expansion`/`New-Logo` → `pot.get(name, 0.0)==0` → NaN, and that NaN path is NOT marked `structural`, so the flight looks like a knob-reachable miss. Criterion accepted at Gate 1 despite dimension↔plan-unit↔column incoherence; P1.4 ceiling only covers tier_share_shift. **S22.2 [CALIBRATION/KNOB-SHAPING GAP]:** AC3 `tier_share_shift` two-bound (premium Q1 20% → Q4 30%) oscillated 11%-42% across iterations — proposer's levers (weights_by_quarter, price_multiplier) move Q1+Q4 together so both bounds never land; realizable in principle (per-quarter shaped weights) but no solver shapes two bounds. AC1/AC2 (revenue_vs_plan by segment, raking) landed +2pp every iteration — engine side healthy. |
| 23 | **LANDED** | 1 (+hardening) | 3/3 criteria, all margins positive: AC1 deal_size_decline -43.5%→-56.7% (target -50%±8pp), AC2 win_rate_flat_anchored 2.80pp→2.40pp dev (≤3pp), AC3 data_sanity clean. Landing survived the margin-hardening round. Unassisted. |
| 24 | escalated (stale set) | 10 | **S24.1 [PROXY-CRITERION ACCEPTANCE]:** the story claim "revenue on orphaned accounts became visibly unpredictable" is a VOCAB_GAP (no volatility/variance primitive exists) — the drafter substituted `revenue_concentration` (top-3 ≥ 60%), which the coverage guard flagged TWICE as PARAMETRIC/VOCAB_GAP but proceeded (notes are non-blocking). The accepted criterion doesn't express the claim's substance. **S24.2 [FEASIBILITY CEILING]:** top-3-of-40 won deals ≥ 60% revenue share is NOT achievable by this engine — outlier_deals caps outlier value share at `s×m/(1+s×(m-1))` ≈ 41% max (15% share × 4x), and observed top-3 share plateaued ~43-45% across 10 iterations (sigma 0.7→1.1, median 85k→100k, outlier 4x/0.15 all tried). P1.4 ceiling lint covers tier_share only, not revenue_concentration. AC1/AC2/AC4 (unowned_account_share, engine-synthesized ownership block) landed comfortably (+28pp to +34pp) every iteration. |
| 25 | escalated (stale set) | 7 | **S25.1 [INFEASIBLE GROWTH TARGET]:** AC2 `core_vs_headline_growth` drafted `min_headline_growth_pct=101` — requires ~2x YoY headline growth, but raking pins total revenue to plan (flat YoY by construction), so the margin sat at -101.00 for all 7 iterations. Drafter translated an *attainment beat vs plan* (AC1's 101% attainment PASSED every iteration) into a *growth* parameter. Growth ceilings not covered by the P1.4 lint. **S25.2 [FEASIBILITY CEILING, same family as S24.2]:** AC3 top-5-of-308 deals ≥ 70% share peaked at 62.9%; raising outlier multiplier 40→120 spread value across MORE outliers and made it worse (46-48%). **S25.3 [VACUOUS CRITERIA ACCEPTED at Gate 1]:** AC4 `avg_price_by_tier` with `max_avg_realized_usd=1,000,000,000` (a $1B cap on a ~$619k actual — margin +999M) and AC5 `end_of_quarter_effect` with `min_gap_pp=0` (any gap passes) both passed trivially every iteration, inflating the 3/5. Degenerate thresholds accepted without a realizability/strength check. Genuine criteria: AC1 attainment +2.00pp (real), AC2/AC3 infeasible, AC4/AC5 vacuous. |

**Cohort 21-25 tally:** 1 LANDED (23), 4 escalated (21 structural-order-block after a genuine 4/4 pass; 22 NaN-dimension + two-bound oscillation; 24 proxy-criterion + concentration ceiling; 25 infeasible-growth + concentration ceiling + vacuous passes). Landing rate 20% — matches the P5-era 20% (3/15) headline on the 11-15 subcohort, and is the same as the pre-P5 aggregate, but every death this wave is honest, cheap, and names a NEW realizability surface the gate does not yet cover. Confirmed GENERALIZABLE fixes that hold on fresh ground: unknown-check rejection, engine segment default, geometry re-draft, tier-share ceiling, rising-capacity, elasticity solver, cohort expressions, deal-count floor, margin noise note — none fired spuriously here. New uncovered surfaces (NOT fixing, per protocol): quota_vs_potential dimension↔plan-unit NaN not flagged structural (S22.1); two-bound tier_share shaping (S22.2); revenue_concentration top-N ceilings (S24.2/S25.2); core_vs_headline_growth growth-ceiling feasibility (S25.1); degenerate/vacuous thresholds at Gate 1 (S25.3); structure-check column-order tolerance (S21.1). All parked in the findings above; landing-set preservation re-fly still pending.
| 23 |  |  |  |
| 24 |  |  |  |
| 25 |  |  |  |
