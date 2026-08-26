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
