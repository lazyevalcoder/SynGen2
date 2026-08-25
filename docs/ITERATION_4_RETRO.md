# M5 Iteration 4 — Retrospective & Optimization Queue

> Written 2026-08-25 at the C/D/E build-phase + workstream-C landing checkpoint.
> Purpose: capture what live landings taught us so iteration 5 optimizes
> evidence, not memory. Scorecard at writing: 15/25 scenarios landed.

## What happened

- Offline build: all three workstreams landed as primitives (WS1 rest,
  WS7 temporal entities, WS8 mixtures/elasticity) with 247 tests green and
  byte-identical reproducibility for existing sessions (named streams only).
- Live landings, workstream C: #19 (2/2), #10 (4/4), #15 (5/5),
  #4 (4/4), #1 (6/6). Every session needed human amendment of
  simulator.json / criteria.json after the drafter converged or escalated.

## Reflections

### R1 - Drafter vocabulary lag is the bottleneck, not the engine

The engine could express every story; the drafter didn't reach for the new
blocks. Observed failure modes:
- Skipped new blocks entirely (#19, #10 - no capacity block drafted).
- Expressed new-primitive claims in OLD vocabulary with degenerate knobs
  (#4's whitespace claim as open-pipeline coverage checks; #1 used
  `sigma: 3.195` -> billion-dollar deals, and Q4 `share_open` of 0.85 ->
  unsellable raking strata).
- Criteria drafting missed the new checks even when the story's computable
  claims mapped 1:1 onto them.

Escalations were honest (named the gap instead of faking), which validates
the architecture - but M2's "fresh user lands unassisted" bar does NOT hold
for stories that need new primitives.

### R2 - New primitives are closed-form; calibration should solve them

Effective capacity ((A-R)+R*p/100)/P, quota/potential ratios, ex-whale
raking splits - all deterministic algebra solved by hand in every session.
This is exactly iter 3's pre-flight auto-calibration theme extended to the
iter-4 blocks. If the solver emits capacity blocks sized to the story's
claimed percentages, the amend loop disappears for these claims.

### R3 - Check semantics are only proven by live stories

`headcount_growth_placement` originally ranked units by revenue-per-rep;
live plan sizes made that mis-rank silently (WS territories with big plans
÷ tiny crews looked "strong"). Re-ranked by first-quarter booked revenue -
which also matches the stories' own language ("historical bookings").
Lesson: a check passing synthetic fixtures is necessary, not sufficient.

### R4 - Escalation -> primitive conversion held again

F28 (per-territory market_potential_usd overrides): potential was
proportionally locked to pipeline sampling (both follow region weights),
leaving potential_coverage_gap with no expressible signal. Fixed same
session via affine remap on the existing named stream - zero repro risk.
F29 (open-value composition by stage/potential) has NO primitive yet;
deferred honestly rather than forcing a fake criterion (#1 landed 6/6
without it).

### R5 - Process friction worth burning down

- Session workbook path bug: `syngen generate <session config>` writes to
  cwd-relative path, not the session folder - cost a cycle in s19. Pin
  absolute paths or resolve relative to the config file.
- Batch mode + manual amendment worked well as a human-in-loop pattern,
  but each amendment was algebra the machine should have done (see R2).

## D/E landing-phase addendum (2026-08-25, later same day)

All remaining scenarios landed: #24 #9 #13 #14 #2 #22 #25-finish #16 #17
#3 -> scorecard 25/25. New findings from these ten sessions:

### R6 - Vacuous convergence is a real gate hole

#24 "landed" 0/0 (zero criteria drafted); #9 and #13 converged 2/2 and 3/3
on generic data_sanity / creation_volume_trend criteria that expressed none
of the story's claims. The loop declared victory while expressing nothing.
Fix for iter 5 (queue item 0): a **coverage guard** - refuse convergence
when no criterion maps to the story's computable claims, and criteria-draft
few-shots per check so the drafter reaches for unowned_account_share /
post_change_revenue_decline / forecast_vs_actual etc. by default.

### R7 - Schema listing works for *familiar-shaped* blocks only

The drafter used quota.by_motion UNPROMPTED (resembles the known quota
pattern) but never once reached for capacity / ownership / activity /
forecast without human amendment. Few-shot effort should be spent exactly
on the never-used blocks, not spread evenly.

### R8 - Pin plans to natural revenue before any tier-mix tuning

Under motion-raking, tier revenue shares responded non-linearly to count
shares because rounding-residual absorption dumped big adjustments onto
single deals whenever plan targets sat far from natural revenue. Re-pinning
plans to measured naturals (k ~ 1) restored the textbook multiplier
calculus (entry/premium solves landed within one iteration). Playbook:
measure naturals at attainment 1.0 FIRST, set plans = naturals, then tune.

### R9 - Live stories hardened two more checks

activity_potential_misalignment originally compared against potential-value
share (biased baseline: bottom half of a uniform distribution holds ~25% of
value); re-based on account-count fair share. post_change_revenue_decline
moved from mean-of-per-account-percentages (noise-dominated) to aggregate
dollar-weighted group growth. Same lesson as R3, twice more.

### R10 - Criteria sets need coherence reasoning

s25's drafted AC3 (top-5 deals >= 45% of revenue) was mathematically
incompatible with its own AC1/AC2 (headline 101% / ex-whale 90% implies a
whale budget of exactly 11 points). No knob fix can satisfy an incoherent
set - the drafter burned its proposal cap on it. Iter 5: pre-flight
coherence check on derived quantities (whale budget, weighted attainment)
before the loop starts.

### Engine additions made during D/E landings

- F28 follow-up: `outlier_deals.share_by_quarter` (period-varying whale
  concentration; in-loop pick + replay kept consistent).
- New check: `activity_potential_misalignment`.
- Bugfix: raking now honors `attainment_by_motion` (was silently ignored -
  attainment fell back to 1.0).

## Iteration 5 optimization queue (evidence-backed)

0. **Coverage guard against vacuous convergence** (R6): the loop must not
   declare STORY LANDED on zero or generic-only criteria.
1. **Prompt few-shots per new block** in simulator_draft.txt + criteria-draft
   prompts; keyword-triggered capability hints (headcount/ramp -> capacity;
   unowned/handed over -> ownership; forecast number vs actual -> forecast).
   Prioritize the never-used blocks (R7).
2. **Extend pre-flight auto-calibration solvers to iter-4 primitives**:
   effective_capacity sizing, quota_vs_potential ratio targeting,
   attainment_ex_outliers two-step split, ownership/activity curve fitting,
   and plan-pinning to natural revenue before mix tuning (R8).
3. **Criteria coherence check** (R10): verify derived quantities (whale
   budget = headline - core; weighted attainment across units) can
   simultaneously satisfy all drafted criteria before iterating.
4. F29 primitive: open-pipeline value composition by lifecycle stage and
   account potential tier (needed by #2's "commit in no-engagement deals"
   and #17's leading-indicator claims beyond what core_vs_headline covers).
5. Fix session-path resolution (R5).
6. Then the standing iter-5 scope: knob-delta proposer (G3), margin-aware
   convergence (G4), packaging (installable CLI, README, prompt library).

## Landing record (all 25/25, 2026-08-25)

- Iter 1-3: #6, #7, #8, #12, #18, #20, #23, #5, #11, #21
- Iter 4 C: #19 (m5i4s19), #10 (m5i4s10), #15 (m5i4s15), #4 (m5i4s4),
  #1 (m5i4s1)
- Iter 4 D: #24 (m5i4s24), #9 (m5i4s9), #13 (m5i4s13), #14 (m5i4s14),
  #2 (m5i4s2), #22 (m5i4s22)
- Iter 4 E: #25-finish (m5i4s25b2), #16 (m5i4s16), #17 (m5i4s17)
- Re-run: #3 (m5i4s3) - originally escalated in iter 2, landed first try
  with full vocabulary after one catalog re-pin.
