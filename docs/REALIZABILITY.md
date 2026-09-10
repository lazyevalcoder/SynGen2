# SynGen — Realizability Guarantee (P8)

*Written 2026-09-10. Design of record for the P8 wave, decided after the
P7 re-fly of the three remaining P6 deaths (scenarios 21/22/25; see
`experiments/fly_benchmark/findings_v4.md` addendum 3).*

## The problem this solves

The stage diagnosis (`experiments/fly_benchmark/findings_stage_diagnosis.md`)
found that 75% of flight deaths *surface* at Stage 5 (the tuning loop), but
the root cause is **acceptance**: criteria are signed off that the generator
cannot truthfully build (an impossible target, a measure that cannot fail, a
wrong reference, or a nonexistent unit). P7 closed the loop by routing a
Stage-5 escalation *back* a stage (criteria or config). The re-fly then
exposed what P7 does not reach:

- **S21.2** — the concentration solver wrote `sigma > 4.0` (outside its own
  config domain) for an unreachable target, so the corrective re-drafts
  dead-looped on an invalid config. A deterministic defect, not criteria.
- **S25.4** — `criteria_consistency` fires at Gate 1, before delivery, and
  was terminal after one re-draft; the P7 loop never saw it.
- **S24.2/S25.2/S25.1/S25.3** — concentration and growth ceilings, and
  vacuous thresholds, were accepted (parked from P6).
- **S21.1/S22.1** — a column-order false-negative at the structure gate, and
  a NaN coordinate that masqueraded as knob-reachable.

## The guarantee

> Every flight either **lands**, or **re-expresses itself to a reachable,
> still-faithful form and lands**. It can never dead-loop on an invalid
> config, never pass vacuously, never die at a gate the correction loop
> cannot reach, and never escalate without naming the exact engine limit.

This is not "accept anything". The anti-goalpost floor (P7: the coverage
guard re-verifies every original claim; a revision that drops a claim is
rejected) and the critic remain in force. What changes is that acceptance
becomes *provable* rather than *hopeful*.

## The four gates

1. **Reachability (envelope).** `syngen/packs/revops/envelope.py` is the one
   source of truth for each metric's achievable range, computed from the
   config. `criteria_lint` (`cross_lint` → `_feasibility_findings`) checks
   every criterion against it; an out-of-range target becomes a HARD finding
   that feeds the existing bounded corrective re-draft, which re-expresses
   the claim to a reachable band.
2. **Strength (anti-vacuity).** `criteria_lint.lint_criteria_internal`
   rejects thresholds that cannot fail (a cap no data approaches, a
   `min_gap_pp=0`, a one-sided bound that excludes nothing) as HARD at
   Gate 1.
3. **Coherence (coordinates).** A metric coordinate that resolves to no data
   (NaN ratio, absent unit) is marked **structural**, not a knob-reachable
   miss, so the loop never burns its budget chasing infinity.
4. **Coverage (loop).** Every escalation kind is routable: the bounded,
   claim-preserving rework judge (P7) now also covers Gate-1
   `criteria_consistency`, and the structure gate compares column *presence*
   (order is not part of the contract).

## Solver discipline (the contract every solver must meet)

Deterministic autocalibration (`syngen/phases/preflight.py`) must:

- **stay inside the config domain** (`config.py`): never write a value the
  loader will reject;
- **use every lever** before declaring a target infeasible; and
- **never silently no-op** on a criterion it cannot satisfy.

The concentration solver is the worked example. The original bug: it raised
`deal_size_lognormal.sigma` past the hard cap of 4.0 for a target it could
not reach, producing an invalid config that dead-looped the corrective
re-drafts (S21.2). It now solves within the sigma domain and, when sigma
alone cannot reach the target, raises the **outlier multiplier** — the
engine's dominant concentration lever, which has no upper bound
(`config.py` requires only `> 1`). So concentration targets are reachable
in practice, and are **not** hard-gated as "unreachable".

A subtlety worth recording: a sigma-only estimator badly under-predicts
concentration because it ignores the outlier lever (cert s21: model
predicted 52%, engine realized 96.9%). The estimator is now
outlier-faithful, which matters for solving accurately and for never
false-killing a reachable target.

## Envelope functions (v1)

| Function | Metric | Basis |
|---|---|---|
| `pipeline_top_share(cfg, sigma, topn, outlier_mult=None)` | top-N account share of open-pipeline value | seeded Monte-Carlo mirror of the engine: per-quarter lognormal sizes, outlier scaling, open cohort, uniform accounts |
| `pipeline_concentration_ceiling(cfg, topn)` | reference share at `sigma = 4.0` with the *current* multiplier | not a hard ceiling — the multiplier is unbounded |
| `headline_growth_ceiling(cfg)` | first→last-quarter won-revenue growth | revenue is raked to plan × attainment, so growth is pinned by the plan curves (a **true** ceiling) |

## Verification

- Full suite: **399 green** (20 new in `tests/test_p8_realizability.py`).
- Targeted re-fly of the tricky/failed scenarios (21, 25) on this branch;
  the full 25-story certification is the weekend run.

## Scope boundary

Concentration is handled by the solver (two levers), not by a hard gate,
because its outlier lever is unbounded. The growth ceiling is a true
arithmetic ceiling and is gated. Remaining additions tracked here: an
explicit infeasibility signal for the capacity solver, and routing any
future deterministic "cannot solve" path through the same finding
mechanism rather than a silent no-op.

## P9.1 — Drafter authoring guide ("skills")

The dominant remaining variance is the *drafter*: the LLM invents different
criteria each run, some unreachable or mis-scoped, so "verify it lands" is a
re-roll rather than a fix. P9.1 reduces that variance at the source.

- **Curated doctrine** — `packs/revops/prompts/authoring_guide.txt`: scope
  only real units (no pseudo-cohorts), match the claim's direction, never
  draft a threshold that cannot fail, stay within what the engine can build,
  one criterion per claim.
- **Generated facts** — `PackTaxonomy.authoring_guide()` renders, from the
  signature registry, the valid coordinate spaces per check and the
  `directional_params` / `pinned_quantity` notes. Generated, so the rules
  cannot drift from what the engine can actually build.
- **Injection** — `{{authoring_guide}}` is added to `decompose.txt` (the
  criteria drafter, via `intake.draft_criteria`) and `rework_judge.txt` (so
  re-expressions aim at reachable forms, via `rework.judge_revision`).

This is prompt-level and probabilistic: it reduces bad drafts but does not
guarantee. The guarantee remains the deterministic layer (P9.2, next:
a Gate-1 reachable-target clamp for provably-unreachable targets).

Verification: full suite **402 green** (3 new tests in `tests/test_packs.py`
assert the guide renders curated + generated facts and that both prompts
substitute it with no leftover placeholder).

## P10 — Measurement & cost (steps 1-2)

Before spending on external tokens, two small, local-first capabilities:

- **Step 1 — token accounting.** `LLMClient` accumulates per-flight usage
  (`calls`, `prompt_tokens`, `completion_tokens`, `total_tokens`,
  `elapsed_s`); `run_fly` writes it into `fly_report.json` and
  `summarize_reports` aggregates it into the fleet summary. The local
  endpoint already returns usage, so a 10-scenario local run yields the
  tokens-per-flight budget picture without external spend (tokenizer counts
  differ from hosted models by ~10-30%).
- **Step 2 — criteria probe + skills A/B.** `syngen/probe.py` runs stages
  1-2 (+ optional config/calibration/geometry) and STOPS before the tuning
  loop, reporting Gate-1 survival, reachability, and failure classes.
  `scripts/ab_skills.py` runs the probe with/without the P9.1 guide, K runs
  per story, and aggregates pass rates + token cost per arm. This measures
  whether skills actually helps, cheaply, instead of guessing from n=1.

    python scripts/ab_skills.py --limit 5 --runs 3 --with-config

Suite 407 green; 5 new tests in `tests/test_probe_skills.py`.
