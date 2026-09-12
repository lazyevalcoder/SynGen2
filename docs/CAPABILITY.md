# Capability Workbench (experiment)

> Branch: `exp/capability` (stacked on `exp/defect-response`). Opt-in:
> `run_new_story(..., use_capability=True)`. Default path unchanged.

## The idea
The drafter was given a **rulebook** (5.5k chars of prose) and then graded.
This gives it the **tools** instead: the engine's real numbers, a calculator,
and a sandbox. The intern isn't short on rules; it's short on tools.

## What the drafter gets

**Context — a capability sheet (numbers, not prose)**
`capability.capability_sheet()` replaces the rulebook in the `decompose`
prompt: hard limits (blocked/pinned checks), reachable ranges, and directional
signs. **5,492 → 2,391 chars** and it is *signal*, not doctrine.

**Tool — a reachability estimator**
- `assess_criteria(doc, cfg=None)` — per criterion `reachable / predicted /
  nearest`.
- `assess_config(cfg, doc)` — once a config exists, the **gap**: predicted
  value vs target, and the nearest buildable value.

Closed-form checks only (reusing the existing math, no new physics):
`core_vs_headline_growth` (raking ceiling), `pipeline_concentration`,
`tier_share_shift`, `avg_price_by_tier`, `quota_vs_potential` (blocked),
`revenue_vs_plan` (pinned), `effective_capacity` (≤100). Anything else returns
`reachable=None` and falls through to the existing gates.

**Environment — a bounded draft → estimate → revise loop**
`pipeline._capability_workbench` (stage 2/3, after the config draft):
1. assess → for each unbuildable criterion, hand the drafter a **number**
   ("target 105 → use 100"), claim-preserving re-draft (up to **3 rounds**);
2. then a **single deterministic snap** clamps anything still out of range and
   records the adjustment (shown at Gate 1).
Structural bound: the loop is `for round in range(max_rounds)` then one snap
pass — it **cannot run infinitely**.

## Replay result (18 recorded sessions, `scripts/ab_capability.py`)

| | |
|---|---|
| Context size | rulebook 5,492 → capability sheet **2,391** chars |
| Sessions with unbuildable criteria | **4** |
| Unbuildable criteria (before → after) | **6 → 2** |
| Affected sessions fully fixed | **2 / 4 (50%)** — 17 and 22 |
| Cost on already-buildable sessions | **0 tokens** (no-op) |

- Scenario **22** (`blocked_path`) and **17** (two ceilings) were made fully
  buildable; **10** went 2→1 (one snapped).
- **15** remained — a blocked path with no nearest value; the re-draft didn't
  fix it.
- Scenario **25**'s `dimension='ex_outliers'` is a *geometry* error, outside
  the capability assessor's reachability scope (the existing geometry lint
  handles it).

## Honest limits
- Closed-form checks only; unknown checks get qualitative facts, no number.
- Replay of the workbench step only — a buildable set hasn't been proven to
  land the whole flight.
- The gap is only as good as the envelope math (which now has shared helpers,
  `envelope.tier_share_ceiling` / `avg_price_by_tier`, so the lint and the
  tool agree by construction).

## Files
- `syngen/capability.py` — sheet, assess, snap.
- `syngen/packs/revops/envelope.py` — shared `tier_share_ceiling`,
  `avg_price_by_tier`.
- `syngen/phases/intake.py` + `packs/revops/prompts/decompose.txt` — the sheet
  replaces the rulebook.
- `syngen/pipeline.py` — `_capability_workbench`, `use_capability` flag.
- `syngen/fly.py`, `scripts/bench_fly_parallel.py` — `--use-capability`.
- `scripts/ab_capability.py` — replay harness.
- `tests/test_capability.py` — 7 tests.

## Next
1. Full-fly A/B on the hard cases (22, 15, 17) with `--use-capability`.
2. Cover more checks with closed forms as they recur.
3. Then consider flipping the default.
