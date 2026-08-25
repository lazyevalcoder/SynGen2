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

## Iteration 5 optimization queue (evidence-backed)

1. Prompt few-shots per new block in simulator_draft.txt + criteria-draft
   prompts; keyword-triggered capability hints (headcount/ramp -> capacity;
   unowned/handed over -> ownership; forecast number vs actual -> forecast).
2. Extend pre-flight auto-calibration solvers to iter-4 primitives:
   effective_capacity sizing, quota_vs_potential ratio targeting,
   attainment_ex_outliers two-step split, ownership/activity curve fitting.
3. F29 primitive: open-pipeline value composition by lifecycle stage and
   account potential tier (needed by #2's "commit in no-engagement deals"
   and #17's leading-indicator claims beyond what core_vs_headline covers).
4. Fix session-path resolution (R5).
5. Then the standing iter-5 scope: knob-delta proposer (G3), margin-aware
   convergence (G4), packaging (installable CLI, README, prompt library).

## Remaining landings (D/E cluster)

#24 (ownership proof) -> #9 -> #13 -> #14/#2 -> #22 -> #25-finish ->
#16 -> #17 -> #3 (escalated-once re-run with full vocabulary).
