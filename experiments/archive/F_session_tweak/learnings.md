# Experiment F — Learnings

## Result: GATE PASS

The retention/replay promise works: a story tweak resolved to **config-only changes**, regenerated a dataset with **identical structure but different values**, and re-converged in one loop iteration.

## What was proven
1. **Same structure, new story:** sheets/columns byte-identical in shape; values moved exactly where the story demanded (Q4 discount 19.16→21.16%, CSB segment materialized as 9 accounts / 239 opportunities).
2. **Zero code changes:** only simulator.json + criteria_amended.json were touched.
3. **Determinism preserved:** seed unchanged; untouched quarters (Q1–Q3 win rates, discounts) reproduced identically — proof that partial tweaks don't destabilize the whole dataset.

## New finding: criteria dependency propagation
The most valuable failure of the experiment: amending AC3 (Q4 discount 18→21%) silently invalidated AC7 (realized/list end target 82% is just 100−18). First run scored 7/8 until AC7's implied amendment was applied.

**Implication for the harness:** the story-diff classifier cannot be a simple knob-mapper. It needs a **criteria dependency graph** (AC7 = f(AC3)) so amendments propagate. This is now a contract requirement: criteria.json should declare `depends_on` edges, or the diff step must run an LLM consistency check over the amended set before Gate 1 re-approval.

## Diff taxonomy validated
| Story change | Classification | Path |
|---|---|---|
| "Q4 worse" | parametric tweak | Phase 4 loop only |
| "add CSB segment" | taxonomy addition | simulator.json edit, no structural change |
| "track deals separately from opportunities" | structural | would require Phase 2/3 revisit (not exercised — future edge case) |

The third class remains untested and is the boundary of this experiment's claims.

## Disposition of original concern #1 (session folders & tweaks)
**Addressed.** Session layout contract still needs writing into ARTIFACT_CONTRACTS.md (done in doc update), and the diff classifier is now a named component with a validated happy path.
