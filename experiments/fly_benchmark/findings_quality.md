# Data Quality Audit - "landed" does not mean "correct"

> A landing only means every criterion PASSED. It says nothing about whether
> the generated data is realistic or faithful to the story's stated magnitude.
> This document identifies the quality failures hiding behind green checks.
>
> Sources: per-flight `validation_report.md` in
> `experiments/fly_benchmark/run_7-12/sessions/` and
> `run_19-25/sessions/` (raw reports gitignored).
> No fixes here - identification only.

---

## 1. Headline: two landed flights contradict their own story

| Scenario | Story says | Landed data says | Margin |
|---|---|---|---|
| **21** | "Pipeline coverage remained **healthy at 3.5x**" | **65.0x** (Q2), **83.2x** (Q3) | **+61.5**, **+80.2** |
| **21** | "significant **dependency on fewer deals**" | top-5 won share **74.8%** | +34.8 |
| **09** | "declined **noticeably** / **materially weaker** growth" | owner-changed **-58.5%** vs stable **-1.0%** | **+45.6**, **+49.6** |

Scenario 21 is the clearest case: the story states 3.5x coverage; the dataset
is 18-24x that. The criterion name is "aggregate coverage healthy at 3.5x",
but the check is `coverage_ratio min_multiple: 3.5` - a lower bound - so a 65x
overshoot passes cleanly.

---

## 2. The pattern: one-sided bounds cannot detect overshoot

Every sane landing used a **two-sided** check (`target +/- band`). Every wild
margin came from a **one-sided** check (`>=` / `<=`).

| Bound type | Checks (examples) | Observed margins |
|---|---|---|
| Two-sided (`target +/- band`) | 08 all; 12 all; 20 all; 21 AC5; 07 AC1/AC3 | 0.28 - 5.0 |
| One-sided (`>=` / `<=`) | **21 AC1/AC2/AC4/AC6**; **09 AC1/AC2**; 11 AC2/AC5; 07 AC2; 12 AC4/AC5; 20 AC7 | up to **+80.2** |

The huge margins are exclusively one-sided. One-sided checks are effectively
"at least / at most" and give the tuning loop an unbounded direction to run.

### Full landed margins

| Scenario | Result | Margins | Offender? |
|---|---|---|---|
| 07 | 3/3 | +5.00, +4.32, +3.76 | no |
| 08 | 8/8 | +0.53 .. +3.41 | no |
| 09 | 2/2 | **+45.55, +49.55** | **YES** |
| 11 | 6/6 | +1.21 .. +8.00 | borderline (AC1 +8.0) |
| 12 | 6/6 | +0.70 .. +5.00 | no |
| 20 | 8/8 | +0.28 .. +3.00 | no |
| 21 | 6/6 | **+61.51, +80.20, +34.83**, +10.37 | **YES** |

---

## 3. The mechanism (scenario 21): trading one one-sided check for another

1. AC3 `pipeline_concentration` (top-5 >= 50%) failed at 26.4%.
2. The loop raised `outlier_deals.multiplier` 20 -> 45 and `share` 0.02 -> 0.05
   (proposal 1), inflating open-pipeline value until concentration passed.
3. Coverage (`>= 3.5x`, **no upper bound**) exploded to 65x/83x.
4. Result: 6/6 PASS, but the dataset no longer resembles the story at all.

Nothing in the criteria set stopped the blow-out, because coverage had no
ceiling and concentration had no ceiling either.

---

## 4. One-sided checks in the registry (candidates for range-bounding)

- `coverage_ratio` - `min_multiple` only (no `max_multiple`).
- `pipeline_concentration` / `revenue_concentration` - `min_top_share_pct` only.
- `slippage_trend` - `min_increase_pp` only.
- Gap/differential checks (e.g. scenario 09's ownership-growth gap) - `min gap`
  only, so an arbitrarily large collapse passes.

Contrast with `forecast_vs_actual` / `revenue_vs_plan` / `blended_margin`,
which use `target +/- band` and produced the tightest, most faithful landings.

---

## 5. Recommendations (identification only)

1. **Range-bound point-estimate claims.** When the story names a magnitude,
   encode that magnitude `+/- band`, not `>=`. Coverage "healthy at 3.5x" ->
   `~3.5x +/- band` (or `[3, 5]`); "small number of deals" -> a band, not a
   floor; "materially weaker" -> a bounded gap, not `>=`.
2. **High-side margin sanity.** There is a `thin_margins` concept for narrow
   passes; the opposite (passing by 30-80pp) is equally a red flag that the
   data does not match the claim. A "loose margin" warning would have flagged
   09 and 21 immediately, at delivery time.
3. **Name/check agreement lint.** Criterion names frequently state a point
   ("healthy at 3.5x", "missed plan by 3pts") while the params only enforce a
   bound. A cheap deterministic lint could compare the two and flag the
   mismatch.
4. **Cross-criterion blow-out guard.** When a proposal moves a lever to satisfy
   one criterion, re-check that no already-passing criterion drifts far past
   its target. Scenario 21's coverage blow-out was visible in the same
   iteration it happened.

---

## 6. Clean vs offender landings

- **Clean / faithful:** 07, 08, 11, 12, 20 (max margin <= ~7pp; two-sided
  checks dominate).
- **Offenders:** 09 (57.5pp growth gap), 21 (18-24x coverage overshoot).

---

## 7. Run context

Batch 19-25 was interrupted: 19, 20, 21 completed (20, 21 landed; 19 stalled);
**22 hung in an unbounded draft-retry recursion** (`spec.py:48`,
`quota.by_motion['New_Logo']` vs `'New Logo'`) and was killed; 23-25 never ran.
So this audit covers landed flights from 7-12 and 19-21 only.
