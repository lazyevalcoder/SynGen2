# P17: closing the observed failures

> Status: implemented on `refactor/stage23-phases` (2026-09-12). 512 tests
> green. No scenario runs after these fixes yet.

Maps each open failure from the DeepSeek/local experiments to its fix.

| # | Failure | Fix |
|---|---|---|
| 5 | `quota.attainment` keys don't match the chosen quota dimension (`attainment['Enterprise']` with `by_territory`) | `buildability.cross_block_findings` now checks attainment maps against the chosen `by_*` units; `quota.txt` states it. Targeted re-draft fixes it. |
| 7 | Knob proposer emits schema-invalid configs | Already rejected by the content gate; rejected paths are now fed back into `history_lines` as `REJECTED=... (do NOT propose these again)`. |
| 8 | Knob proposer invents schema keys (`market_potential_usd.high_pot_min`) | `converge._apply_changes` rejects a NEW leaf key on an existing object unless it is a known optional addition (`_KNOWN_NEW_LEAVES`); creating through null containers still works. |
| 9 | Checks whose levers are non-tunable stall the loop | `converge._NON_TUNABLE_CHECKS` + an early `not-loop-recoverable` escalation after all deterministic remedies run. |
| 10 | Proposer tries blocked/non-tunable paths | `knob_proposal.txt` now lists the tunable paths and the forbidden ones. |
| 11 | Same-stage failures are terminal | `runner.run_stages` retries when `rewind_to == current stage` (bounded by `max_rewind_rounds`), not only when `<`. |
| 12 | Rewind re-draft trades one failure for another | Improved by #11 (retry) + the buildability gate. |
| 13 | Blocked check has no replacement | `check_signatures.json` gains `replacement` (`quota_vs_potential` -> `potential_coverage_gap`); `menu.replacement_for`; `menu_findings` names it. |
| 14 | Coverage-guard churn on blocked-only claims | `intake._normalize_audit_item` maps a blocked suggested check to its replacement (PARAMETRIC) or degrades it to a VOCAB_GAP note (no churn). |
| 15 | Claim loss / silent downgrade | The menu gate now re-drafts via `rework.redraft_criteria` (coverage re-checked against the original claims); a re-draft that loses coverage is rejected. |
| 16 | Proxy-criterion acceptance (criteria measure the wrong thing) | `stage_criteria` re-runs the critic after its corrective re-draft; a persistent block finding escalates `criteria_intent`. |
| 17 | Near-duplicate criteria | `stage2._dedupe` drops the same `check + coordinate + source_claim`. |
| 18 | Pseudo-units at stage 2 (`"high-potential territory"`, `"small"`) | `menu_findings` flags narrative labels in coordinate spaces (whitespace / known narrative words). |
| 19 | Menu-gate re-draft not claim-preserving | Uses `redraft_criteria(..., menu_constrained=True)`. |
| 20 | PF1 dimension mismatch corrective failed | Improved by #5 + #11. |
| 21 | "Landed but loose" | Existing `loose` flag; surfaced in the validation report. |

## Tests
`tests/test_p13_enforcement.py` (+9) and `tests/test_runner.py` (+1): blocked
replacement mapping, narrative pseudo-unit detection, audit blocked->replacement,
attainment/dimension mismatch, invented-key rejection, non-tunable set,
near-duplicate dedupe, same-stage retry.
