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

---

## P7 addendum (2026-09-09): the flexible stage-rework loop turns deaths into re-landings

After P6, escalations were terminal by design. The P7 rework loop (see
DOMAIN_PACKS.md P7 row) made them *re-routable*: an escalation emits an
evidence packet, an LLM judge routes the next attempt to a claim-preserving
criteria re-draft or a config re-draft (coverage re-verified against the
persisted original claims), bounded to 2 rounds and tagged in the report.

Two random live flights (not a protocol cohort) validate it end-to-end:

| Scenario | Result | rework | Notes |
|---|---|---|---|
| 23 (re-fly) | **LANDED** 4/4 (attempt 3) | 2 rounds, both `rework_criteria` | Drafter drafted a harder contract this run (-50%±5pp the loop could not reach, plus an entry-tier "doubling" the story never quantified). Judge re-expressed AC1 and AC3 with explicit claim-preservation guidance; attempt 3 landed (deal size -54.8%, tier share 25.1%→32.3%, win-rate flat, sanity clean). |
| 24 (re-fly) | **LANDED** 3/3 (iter 6) | 0 rounds (clean) | Previous death was an unreachable top-3-concentration proxy (S24.1/S24.2). This run the drafter expressed the story as `post_change_revenue_decline` (gap ≥10pp) — buildable — and the autopilot landed it (-26.6% changed-owner vs +60.6% stable = +77pp) on the ownership/outlier synthesis. |

Both are tagged (`rework.rounds`) so the scoreboard keeps clean vs reworked
landings honest. No P7 regression: every P6 rule stayed silent; landing-set
preservation re-fly (05/09/11/13/14) still owed.

---

## P7 addendum 2 (2026-09-09): landing-set preservation re-fly — 5/5 LANDED

Run on master after the P6+P7 merge, the promised regression check. All five
preservation scenarios still land (05, 09, 11, 13, 14 — status converged).
Rework rounds required on master (rework loop now enabled): 05→1, 09→1,
13→2, 11→0, 14→0 — i.e. three needed the LLM-judged loop to get there, two
landed clean; all are tagged in their reports.

**The re-fly earned its keep:** scenario_11 crashed with
`NameError: name 'ConfigError' is not defined` — a latent bug in
`pipeline.py` (`calibrate_gate` catches `ConfigError` without importing it;
Python only resolves an except name when an exception is raised, so it lay
dormant until a P6/P7 solver precondition actually raised one on s11). Fixed
with a one-line import (`syngen/pipeline.py`), s11 re-landed. No scenario-
specific change. This is exactly the class of regression a preservation
re-fly exists to catch.

---

## P7 addendum 3 (2026-09-10): re-fly of the three remaining P6 deaths (21/22/25)

The P6 holdout deaths 21/22/25 were flown *pre-P7* (escalation was terminal
then), so they had never been run with the rework loop enabled. This closes
that gap: same build (master, P6+P7), same stories, no new code. Result:
**1/3 landed clean; the two that escalated each name a NEW surface, and
neither was recovered by the rework loop** — for two distinct structural
reasons (below).

| Scenario | Result | Iters | Rework | Notes |
|---|---|---|---|---|
| 22 | **LANDED** | 1 | 0 (clean) | 5/5, no thin margins (AC1 106±2, AC2 97±2, AC3 top-20 92.3% ≥40, AC4 top-10 56.9% ≥55, AC5 sanity). The P6-era death (S22.1 `quota_vs_potential` NaN-dimension + S22.2 two-bound tier-share oscillation) **did not recur** — the drafter expressed the story in a buildable form this run. |
| 21 | escalated | 0 (preflight) | 2/2, both `rework_criteria` | **S21.2 [SOLVER BUG — deterministic]:** `_autocalibrate_concentration` (`preflight.py:1104`) raises `deal_size_lognormal.sigma` to reach a top-N open-pipeline-share target but **does not clamp to the config domain `(0, 4.0]`** (`config.py:143`): its probe loop breaks with `hi > 4.0` and sets `found = hi` anyway, so `sigma` lands at 4.22–4.43 → invalid config → `[PF0] sigma must be in (0, 4.0]` → corrective re-draft repeats the identical over-raise → `HARD findings did not shrink` → early escalate. Repeats verbatim across all 3 attempts and both rework rounds. Two sub-defects: the intended "could not reach … escalating as-is" branch (`found is None`, line 1150) is **dead code** (the `or hi > 4.0` break always sets `found`), and the solver targets `need * 1.08`, which can escape the domain even when the plain target is reachable. The judge reasoned correctly (collapsed redundant concentration checks, caught the forecast-attainment ceiling) but has no engine-envelope knowledge, so every re-expression still needed sigma > 4.0. |
| 25 | escalated | 0 (Gate 1) | none — loop not engaged | **S25.4 [CRITERIA CONSISTENCY, un-routed]:** drafter produced three `revenue_vs_plan` criteria at **101±2, 90±2, 95±3 on the same coordinate** (`segment=_all_`, `dimension=None`) — jointly unsatisfiable. The Gate-1 consistency lint caught it, one corrective re-draft ran (critic accepted), the lint still found the conflict → `criteria_consistency` escalate. The P7 rework loop **does not cover this escalation kind**, so `rework.rounds` is null and the death is terminal. Root: segment-specific claims ("core ran at ~90% of plan") were drafted unscoped onto the `_all_` coordinate. |

**Revised holdout tally (21–25, current build):** 22, 23, 24 LANDED; 21, 25
escalated. (23/24 per addendum 1, 22 here.) Two clean landings (22, 24) and
one reworked (23); 22/24 land on a single iteration.

**Why the loop didn't save 21/25 (the two distinct structural reasons):**
1. **21 — deterministic solver emits an invalid artifact.** The rework loop
   re-drafts criteria, but the *calibrator* re-runs the same broken solve each
   time; no LLM judgment can fix a solver that produces out-of-domain config.
   The fix belongs in the solver (clamp + emit a real feasibility ceiling),
   not the judge.
2. **25 — escalation kind outside the loop.** `criteria_consistency` fires at
   Gate 1, before delivery, and isn't a `preflight_persist`/convergence/delivery
   kind the judge routes on. The consistency lint is terminal after one
   corrective re-draft.

**New surfaces queued (P8):** S21.2 (solver domain clamp + feasibility-ceiling
finding for concentration; generalize the F19.3/S24.2/S25.2 ceiling family to
open-pipeline value concentration); S25.4 (route `criteria_consistency` into
the bounded rework loop, and/or a deterministic coordinate-scoping lint for
segment-specific claims drafted onto `_all_`). **S21.1** (structure-gate
column-order contract bug) remains latent — scenario 21 now dies earlier in
preflight, so the order-only false-negative still hasn't been re-exercised;
still worth fixing (it is the only class that kills a genuinely-landed flight).

---

## P8+P9.1 verification (2026-09-10): 25 and 21 still escalate, but honestly

Ran on the P8 (`fix/realizability-p8`) + P9.1 authoring-guide
(`feat/drafter-skills`) code. Both target scenarios still escalate; neither
is a bad failure - each names a precise, real gap, and P9.1 visibly improved
the judge's reasoning.

| Scenario | Result | Where | What the judge/drafter did |
|---|---|---|---|
| 25 | escalated | preflight (rework 1) | Judge correctly diagnosed the unreachable growth claim (raking pins revenue to plan) and ordered the right *kind* of fix, but suggested `revenue_vs_plan` with `dimension: "ex_outliers"` - which is not a plan dimension. The engine expresses the core-vs-headline split via `exclude_outlier_deals: true`. **Fixed:** that fact is now in the P9.1 authoring guide so both drafter and judge know the reachable form. |
| 21 | escalated | convergence (oscillating) | AC3 `pipeline_concentration` top-5 >= 65% and AC4 `revenue_concentration` top-5 >= 60% were not reached (margins -6.49 / -17.53); proposals traded criteria for 6 iterations. Judge escalated honestly (the story asserts concentration as the problem). |

**Named next gap (P9.2 candidate):** `revenue_concentration` (won-deal
concentration) has NO deterministic solver - only `pipeline_concentration`
does (`_autocalibrate_concentration`). A won-deal concentration target
therefore relies on the LLM proposer and can fail even though the outlier
lever is unbounded. The bounded fix is a `_autocalibrate_revenue_concentration`
that sizes the outlier share/multiplier against the estimator, exactly like
the pipeline-concentration solver. Secondary: the convergence oscillation on
two linked concentration criteria (AC3/AC4) suggests a joint-lever remedy.

**P9.1 status:** implemented and CI-covered (curated doctrine + generated
signature facts injected into `decompose.txt` and `rework_judge.txt`); full
suite 402 green. It is the probabilistic half; P9.2 (deterministic clamp +
the revenue-concentration solver) is the guarantee half.

---

## Addendum 4 - scenarios 7-12 re-fly (2026-09-11): 5/6 landed

Local Ornith-35B (llama.cpp, `--reasoning-budget 4500`), one worker,
`experiments/fly_benchmark/run_7-12/` (raw reports gitignored). This cohort
was flown on master after the P8 realizability guarantee + the P9.1 guide.

| Scenario | Result | Iters | Rework | Notes |
|---|---|---|---|---|
| 07 | **LANDED** | 6 | 1 round (`rework_criteria`, AC2) | Judge caught AC2's unreachable 8pp low-ICP share rise and re-expressed it to the reachable magnitude; then converged. |
| 08 | **LANDED** | 7 | 0 (clean) | |
| 09 | **LANDED** | 1 | 0 (clean) | |
| 10 | escalated | - (preflight) | 1 round (`rework_criteria`, AC4) | See S10.1/S10.2 below. |
| 11 | **LANDED** | 1 | 0 (clean) | |
| 12 | **LANDED** | 8 | 0 (clean) | |

Fleet: 5/6 (83.3%), 116 LLM calls, 509,879 tokens, 3317s LLM time. First
cohort where the rework loop actually *saved* a flight (07) rather than only
diagnosing one.

### S10.1 [DETERMINISTIC BUG] capacity synthesis emits fractional headcount_actual

The capacity-block synthesizer (`preflight.py:1368-1369`) builds a rising
headcount flow for `headcount_growth_placement` with:

    spec["headcount_actual"] = [round(6.0 + qi * 1.5, 2) for qi in range(n_q)]

For n_q=4 that is `[6.0, 7.5, 9.0, 10.5]`. `config.validate` requires
`headcount_actual` values to be **non-negative integers** (`config.py:482-486`),
so the config is HARD-invalid:

    [HARD/PF0] *: config invalid: capacity.by_territory['West'].headcount_actual
    values must be non-negative integers

The synthesizer re-runs after every corrective draft, so each re-draft is
overwritten with the same fractional values -> "no improvement across
corrective drafts" -> terminal preflight escalation. Scenario 10 only hit
this because the drafter omitted a capacity block, so the deterministic
synthesizer (not the LLM) wrote `headcount_actual`.

**Why CI missed it:** `tests/test_p6_realizability.py:166` only asserts the
flow is rising (`actual[-1] > actual[0]`); it never validates the synthesized
config, so fractional values pass.

**Bounded fix (implemented):** integer increments,
`[6 + 2 * qi for qi in range(n_q)]` -> `[6, 8, 10, 12]`; the same integral
fix in `converge.py` `_remedy_headcount_growth`; a `_normalize_capacity_headcounts`
guard in `autocalibrate` that coerces fractional counts and clamps ramping; and
both tests now assert integer validity via `validate_simulator_doc`.

### S10.2 [ROUTING GAP] the judge misdiagnoses a structural PF0 as a criteria ceiling

The escalation surfaced as `preflight_calibration`; the rework judge read it
as "AC4's above-ceiling effective-capacity target is unreachable" and routed
`rework_criteria` at AC4. The real HARD finding was the config-invalid PF0
above - nothing to do with AC4. Criteria rework cannot fix a deterministic
solver emitting invalid config, so the round was spent and the flight
escalated.

Same class as S21.2 (the judge has no engine-envelope/solver knowledge):
when preflight fails on a **structural** PF0 (`config invalid`), it should be
repaired deterministically or surfaced as a solver/config finding - not
routed to criteria rework. The judge's AC4 analysis was itself *correct*
(AC4's `target_pct: 105` does invert the story's "below headline growth"
direction); it is simply not what killed this flight.

**Net:** 10's death is deterministic and cheap (S10.1); S10.2 is the same
open loop already documented in `findings_stage_diagnosis.md` - the rework
loop is open for structural failures.

**Fixed (this change):** the preflight gate now carries the real HARD findings
into the escalation evidence, classifies an all-PF0 failure as
`preflight_structural`, and `_delivery_rework` skips the LLM judge for that
kind (it would misattribute it to a criteria ceiling) - escalating directly
with the structural cause. Non-structural failures still route to the judge.
Two regression tests added in `tests/test_rework_loop.py`.
