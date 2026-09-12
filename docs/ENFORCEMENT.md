# Enforcement: making stages 1-3 output buildable artifacts (P13)

> Status: implemented on `refactor/stage23-phases` (2026-09-12). 492 tests
> green. No live scenario runs yet.

## Why
The 13-16 stage-3 experiment showed the same pattern three times: the system
**knew** a rule (the menu marks `quota_vs_potential` BLOCKED; stage 3 knows
`elasticity_differential` needs `pricing_response`) but only **advised** the
model. Advice is not a wall, so:

- scenario 15 shipped `quota_vs_potential` criteria - the coverage audit
  recommended the blocked check, and the coverage/critic/consistency
  re-drafts used the full catalog;
- scenario 16 shipped a config with no `pricing_response`, and stage 3 still
  reported **completed**.

P13 turns those rules into deterministic walls.

## The three walls

### 1. Menu gate on criteria (stage 2)
`syngen/menu.py`:
- `buildable_check_names()` / `buildable_catalog()` - the menu minus blocked
  checks;
- `menu_findings(doc)` - hard findings for **blocked checks, unknown checks,
  exact duplicates**.

`syngen/phases/intake.py`:
- the coverage audit now receives the **buildable** list plus an explicit
  "never recommend these" blocked list (it can no longer suggest a blocked
  check);
- `draft_criteria` can draft from the buildable catalog only
  (`menu_constrained=True`);
- `syngen/stages.py::stage_criteria` runs a **final menu gate** after every
  re-draft path, with a bounded menu-constrained re-draft, then escalates
  `criteria_menu` (rewind 2) if violations persist.

### 2. Buildability gate at the end of stage 3
`syngen/phases/buildability.py::verify_config(cfg, checks)` - every
criterion's required **blocks** and sub-key **features** must exist in the
assembled config (`accounts.market_potential_usd`,
`opportunities.outlier_deals`, `products`, `pipeline`, `quota`, `capacity`,
`ownership`, `activity`, `forecast`, `pricing_response`).

`stage3.split_simulator`: a missing piece is re-drafted (targeted, bounded);
if it is still missing the stage raises `BuildabilityError` -> stage 3 fails
honestly (`stage3_buildability`, rewind 3). It can no longer "complete" with
an unbuildable config.

### 3. Reachable ranges (stage 2-3 context)
- `envelope.win_rate_noise_pp(cfg)` - the two-sigma noise floor of a
  quarterly win rate; `criteria_lint._win_rate_feasibility` flags a
  `win_rate_flat` band below it (hard).
- `capability` now assesses `win_rate_flat` (noise floor) and notes that
  `elasticity_differential` requires `pricing_response`.
- `menu.engine_limits_for(checks)` is injected into `criterion_params.txt`
  so the number-filling step sees the engine's hard limits for the checks it
  may use.
- Reference estimators added: `revenue_concentration_share`,
  `deal_size_ratio`.

## Scope
The walls apply to the **runner / split** path. The classic `run_new_story`
path is deliberately unchanged (wrap-first; the menu gate adds an LLM call
that would break call-count-pinned tests). Classic gets the walls when it is
migrated onto the runner.

## Verify (next)
```
python scripts/bench_fly_parallel.py --jobs 1 --offset 12 --limit 4 \
    --upto 3 --stage23 split --llm-config llm_configs/local.json \
    --out experiments/fly_benchmark/run_stage3b
```
Expected: 15 ships **no** `quota_vs_potential` (re-drafted or escalated at
stage 2); 16 gets `pricing_response` or fails **at stage 3** with
`stage3_buildability`; no duplicates.

## Files
- `syngen/menu.py` - buildable list/catalog, `menu_findings`,
  `engine_limits_for`.
- `syngen/phases/buildability.py` - `verify_config`, `BuildabilityError`.
- `syngen/phases/intake.py` - buildable coverage audit, `_menu_gate`.
- `syngen/phases/stage2.py` - param-output constraint + exact dedupe.
- `syngen/phases/stage3.py` - buildability gate + targeted repair.
- `syngen/phases/criteria_lint.py` - `_win_rate_feasibility`.
- `syngen/packs/revops/envelope.py` - `win_rate_noise_pp`,
  `revenue_concentration_share`, `deal_size_ratio`.
- `syngen/capability.py` - `win_rate_flat`, `elasticity_differential`.
- `packs/revops/prompts/criterion_params.txt` - `{{engine_limits}}`.
