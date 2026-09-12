# Divide & Conquer: split stages 2-3, consolidate in code (P11)

> Status: implemented on `refactor/stage23-phases` (2026-09-12). Flag-gated,
> default OFF (`stage23="classic"`). 468 tests green. **No scenario runs yet.**

## The idea

Stages 2-3 each asked one huge prompt for a whole artifact
(`simulator_draft.txt` alone was 15,752 chars). The failure class is "criteria
the engine cannot build", and the fix is subtraction, not more advice:

- **LLM writes small pieces; code merges and validates.** Consolidation is
  never another LLM call, or the stuffing returns.
- **The menu enforces.** A blocked check is not offered, so it cannot be
  chosen - this is the enforcement the capability sheet only advised.

## What was built

| Layer | File | What |
|---|---|---|
| Buildable menu | `syngen/menu.py` | per-check `blocked`/`pinned`/`required_blocks`, `menu_text()` prompt context |
| Mechanism registry | `syngen/mechanisms.py` | name -> callable, one `Finding` shape (capability, geometry, consistency, schema, structure, required_blocks) |
| Signature data | `packs/revops/check_signatures.json` | `required_blocks`, `blocked`, `pinned` per check (33) |
| Stage 2 split | `syngen/phases/stage2.py` | 2a claim->form, 2b params, 2c assemble |
| Stage 3 split | `syngen/phases/stage3.py` | 3a required blocks, 3b core + per-block, 3c assemble |
| Block prompts | `packs/revops/prompts/blocks/*.txt` | core, products, pipeline, quota, capacity, ownership, activity, forecast, pricing_response |

### Stage 2
1. `select_claim_forms` - map each computable claim to ONE menu check.
2. `fill_criteria_params` - fill target/tolerance for the chosen checks.
3. assemble + `validate_criteria_doc`; the existing coverage/consistency
   guards still run after. A blocked form is dropped before params.

### Stage 3
1. required blocks derived from the criteria's checks (`required_blocks`).
2. `draft_core` (accounts + opportunities) and one small call per required
   optional block.
3. assemble with deterministic seed/time_model/output, run the existing
   normalizers (`_normalize_quota_keys`, `_renormalize_product_shares_cfg`,
   `_normalize_capacity_headcounts`), then `validate_simulator_doc`.
   One bounded core re-draft on invalid assembly.

## Corrections captured in the data
The old prompt's block checklist was wrong in two places; the registry is
derived from the check code:
- `quota_vs_potential` needs **quota** (not capacity) + `accounts.market_potential_usd`.
- `potential_coverage_gap` needs `accounts.market_potential_usd` (not capacity).

## How to run
```powershell
python -m syngen fly --story-file uat/scenario_15/story.md --stage23 split
python scripts/bench_fly_parallel.py --jobs 4 --stage23 split --use-capability
```
`run_new_story`, `run_fly`, and the bench harness all accept `stage23`
(`"classic"` | `"split"`).

## Scope / limits
- Split applies to the **initial** drafts. Corrective re-drafts inside the
  calibration gate use the split path too; other re-draft paths (geometry,
  capability workbench, rework judge, defect-response) stay classic.
- The classic path is untouched and remains the default.

## Next
1. A/B `--stage23 split` on scenarios 15/16/17/22 (with and without
   `--use-capability`): prompt size, tokens, landing rate.
2. Only then consider flipping the default.
3. Same treatment for `knob_proposal.txt` (7,963 chars, stage 5) if the split
   wins.
