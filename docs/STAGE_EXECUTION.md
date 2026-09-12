# Stage Execution: run, resume, and rewind a flight (P12)

> Status: implemented on `refactor/stage23-phases` (2026-09-12). 480 tests
> green. No live scenario runs yet.

## Why
The old unit of work was "fly the whole story and wait 15-20 min to learn the
outcome." That makes iteration on the expensive early stages (criteria, config)
painful. A flight is now **7 resumable stages**: run a prefix, see exactly what
completed, resume at the next stage, or rewind when a failure is attributable
upstream.

## The stages

| # | Name | Produces |
|---|---|---|
| 1 | intake | `computable_claims.json` |
| 2 | criteria (+ Gate 1) | `criteria.json`, `decisions.md` |
| 3 | config (dials) | `simulator.json` |
| 4 | preflight (calibrate + geometry) | updated criteria/config |
| 5 | converge (the loop) | `output/dataset.xlsx`, `history/` |
| 6 | structure gate + final proof | `validation_report.md` |
| 7 | deliver (Gate 2) | accepted |

Each stage reads its inputs **from the session folder** (never from memory) and
returns a `StageResult`. That statelessness is what makes resume possible.

## Progress state
`<session>/flight_state.json` records per-stage status
(`pending|completed|stale|escalated|aborted`), `next_stage`, `rewind_to`,
attempts, and the flags used (so a resumed stage 4 uses the same
`stage23`/`use_capability` settings).

Legacy sessions without the file get their state **inferred from artifacts**
(`criteria.json`→2, `simulator.json`→3, `history/`→4/5,
`validation_report.md`→6).

## CLI
```
python -m syngen status <session>          # completed / next table
python -m syngen run <session>             # resume at the next incomplete stage
python -m syngen run <session> --all       # run all remaining stages
python -m syngen run <session> --stage-3   # run up to and including stage 3
python -m syngen run <session> --only 2    # run exactly stage 2
python -m syngen run <session> --from 4    # rewind to 4 and run forward
python -m syngen new --story-file uat/scenario_15/story.md --stage-3
```
`--stage-N` is accepted as sugar for `--stage N`. `new`, `fly`, and
`bench_fly_parallel.py` (`--upto`) all accept a stage bound.

## Rewind
On escalation the runner attributes the failure to a stage:

| evidence kind | rewinds to |
|---|---|
| `criteria_coverage`, `criteria_consistency`, `criteria_geometry` | 2 |
| `draft_invalid`, `preflight_structural` | 3 |
| `preflight_calibration`, `preflight_persist` | 4 |
| `structure` | 5 |
| `convergence` (ambiguous) | rework judge → 2 / 3 / escalate |

It re-runs from that stage automatically, **bounded** by `max_rewind_rounds`
(default 2), archiving the pre-rewind artifacts under
`history/stage<NN>_attempt<K>/` and marking downstream stages `stale`. When the
bound is spent it stops with the reason.

## The surgical 2/3 workflow
`--stage-3` is fast: it stops after criteria + config, no 15-min loop. To
iterate on the two LLM stages:
```
python -m syngen run <session> --only 2     # re-draft criteria
python -m syngen run <session> --only 3     # re-draft config
python -m syngen run <session>              # continue 4-7
```
`summarize_reports` now emits a **stage histogram**
(`stage_histogram`: `stage_reached`, `escalations_by_stage`) so "all the
failures are in stages 2/3" is measured, not assumed.

## Limits / next
- Wrap-first: `run_new_story`/`run_fly` classic paths are untouched; the runner
  is the new interface. Migration can follow once the runner is proven live.
- Rewinding to stage 2 re-runs the whole stage (draft + guards), not a
  claim-preserving patch; the defect-response fixer could later be wired in as
  the stage-2 rewind resolver.
- Stages 2a/2b/3a/3b remain internal; only the 7 top-level stages are runnable.
