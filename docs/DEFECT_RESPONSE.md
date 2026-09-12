# Defect-Response Framework (experiment)

> Branch: `exp/defect-response`. Status: experiment. The default pipeline is
> unchanged (`rework_strategy="classic"`); the new path is opt-in.

## Why

The classic rework hands the drafter the **entire prompt** and asks it to
re-read a prose verdict. Measured on scenario 15:

| Prompt | Total | Judge feedback |
|---|---|---|
| Drafter (`decompose`) | 19,005 chars (~4,750 tok) | **405 chars = 2.1%** |
| Config drafter (`simulator_draft`) | 18,184 chars (~4,550 tok) | **240 chars = 1.3%** |

The single fact that would have prevented the biggest failure class
(`quota_vs_potential` is a blocked path) is ~0.7% of the prompt. The drafter
is correct in being told, and correct in ignoring it: the signal is buried.

Separately, replaying the failures showed the classic full re-draft **does not
preserve the story claims**: across 8 failures it kept `source_claim` verbatim
only 37.5% of the time.

## The framework

Borrowed from ITIL incident/problem management and aviation CRM:

- **Role separation:** detector (gates) → diagnoser (judge) → resolver
  (runbook/fixer) → verifier (guards).
- **Minimal work order** instead of the manual.
- **Known-error runbook:** mechanical classes fixed deterministically, no LLM.
- **Targeted change control:** a patch, not a rewrite.
- **Closed-loop verification:** the patch must survive the guards and keep the
  `source_claim` verbatim.

### Work order (the handoff)
```json
{
  "defect_class": "blocked_path | raking_pinned | above_ceiling | one_sided | pseudo_unit | schema_key_mismatch | missing_surface | unreachable",
  "artifact": "criteria",
  "targets": ["AC3"],
  "observed": {"AC3": {"check": "...", "params": {}, "source_claim": "..."}},
  "root_cause": "<judge reason>",
  "fix_intent": "<judge guidance>",
  "allowed": "<facts for ONLY the target checks>"
}
```

### Stages
1. **Triage** — `classify_defect(verdict, evidence)`.
2. **Runbook** — `runbook_fix`: deterministic range-bounding for one-sided
   checks (`coverage_ratio`, `*_concentration`, `slippage_trend`).
3. **Fixer** — one minimal-context LLM call (`fixer.txt`, `fixer` profile):
   receives only the work order, returns a **patch** for the target ids.
4. **Verify** — `verify_patch`: source_claim verbatim, target-only,
   `lint_criteria_internal` clean.

## Implementation map
- `syngen/phases/defect_response.py` — work order, runbook, fixer, verifier.
- `packs/revops/prompts/fixer.txt` — the minimal fixer prompt.
- `syngen/packs/taxonomy.py::check_facts` — per-check facts (subset context).
- `syngen/phases/preflight.py::_normalize_quota_keys` — deterministic config
  canonicalization (quota keys, `_all_` expansion), called from
  `syngen/phases/spec.py`'s draft repair.
- `syngen/pipeline.py` — `rework_strategy="classic"|"defect_response"`.
- `syngen/llm/client.py` — `prompt_chars`/`completion_chars` instrumentation.
- `scripts/ab_fixer.py` — replay harness over recorded failures.
- `tests/test_defect_response.py`, `tests/test_p6_realizability.py` — tests.

## Experiment — replay of 8 recorded failures (2026-09-12)

`scripts/ab_fixer.py` reconstructs each failure's final escalation from its
session and runs the rework step under both arms. The defect column is after
the split/`checks_available` fixes (re-run, defect arm only).

| Metric | classic | defect_response |
|---|---|---|
| Replays | 8 | 8 |
| Patch applied | 62.5% | **75.0%** |
| Lint pass | 100% | 100% |
| **source_claim preserved** | **37.5%** | **100%** |
| Defect addressed (heuristic) | 37.5% | **75.0%** |
| Total tokens | **124,567** | **5,376** |
| Avg prompt chars | **46,206** | **2,114** |

**Headline: the defect arm used ~4% of the tokens and a ~22x smaller prompt,
preserved every source claim, and addressed twice as many defects.** The
runbook fixed scenario 14's one-sided bounds with **zero LLM calls**.

Per-case (`[defect]`): 10, 14 (runbook, 0 tok), 15, 16, 19, 22 all resolved;
17 and 25 are **config** defects (`missing_surface`, `schema_key_mismatch`) —
handled by the deterministic quota normalizer at draft time (below), not by
the criteria fixer.

### Fixes found by the replay
- The fixer reused an existing id (`AC4`) when splitting a target -> the
  verifier now allows fresh-id splits but still rejects touching existing
  non-targets.
- The fixer had no list of alternative checks -> the work order now carries
  `checks_available` (names only, small) and `existing_ids`.

### Config classes handled deterministically
`preflight._normalize_quota_keys` (called in the draft repair) canonicalizes
quota unit keys (case/separators: `New_Logo` -> `New Logo`, `expansion` ->
`Expansion`) and expands a lone `_all_` to the real segments/motions. This
covers the `schema_key_mismatch` / `missing_surface` classes without an LLM.

## Honest assessment
- **Win:** cost (~4%), prompt size (~4%), and claim preservation (100% vs
  37.5%). The noise hypothesis is supported.
- **Good:** defect-addressed 75% vs 37.5%, at a fraction of the cost.
- **Caveat:** replay isolates the rework step; a patch that addresses the
  defect has not been proven to land the full flight. A full-fly confirmation
  on 2-3 scenarios is the next step.

## Next steps
1. Full-fly A/B on 3-5 scenarios with `rework_strategy="defect_response"`.
2. Re-fly 22/25 to confirm the quota normalizer clears the config deaths.
3. Only then consider flipping the default.
