# SynGen

Turn a **business story** into a realistic synthetic dataset with proof.
You give a narrative ("deal size fell by half while win rates stayed flat");
SynGen drafts measurable criteria from it, builds a generator config that can
truthfully realize them, tunes until they pass, and ships the workbook +
a generated validation report. When a target genuinely can't be built, it
escalates honestly — or (since P7) sends the evidence back to an LLM judge
for a claim-preserving re-draft instead of dying.

## Documentation — where to start

| Doc | What it is |
|---|---|
| [`docs/HOW_IT_WORKS.md`](docs/HOW_IT_WORKS.md) | Plain-English tour of the journey (start here) |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Milestones, status, deferred work |
| [`docs/DOMAIN_PACKS.md`](docs/DOMAIN_PACKS.md) | Engineering history P0–P7 (authoritative phase record) |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Design doctrine: phases over artifacts, deterministic floor |
| [`docs/AGENT_ROLES.md`](docs/AGENT_ROLES.md) | "Is intelligence actually needed here?" — where LLM vs deterministic |
| [`docs/ENTITY_SCHEMA.md`](docs/ENTITY_SCHEMA.md) | Data-model schema spec (mirrored by `packs/revops/entities/`) |
| [`docs/ARTIFACT_CONTRACTS.md`](docs/ARTIFACT_CONTRACTS.md) | File/API contracts between phases |
| [`docs/FLIGHT_MODEL.md`](docs/FLIGHT_MODEL.md) | Flight vocabulary: land / escalate / telemetry |
| [`docs/GAPS_AND_RISKS.md`](docs/GAPS_AND_RISKS.md) | Decision + learning log (experiments → code) |
| [`docs/JOURNEY_PLAN.md`](docs/JOURNEY_PLAN.md) | Future work: hero-journey observability |
| [`experiments/fly_benchmark/findings_v4.md`](experiments/fly_benchmark/findings_v4.md) | Live certification record (cohorts 21–25, P7 validation, preservation re-fly) |
| [`experiments/fly_benchmark/findings_stage_diagnosis.md`](experiments/fly_benchmark/findings_stage_diagnosis.md) | Where flights fail, by stage |

**Archives (kept for history, superseded by the docs above):**
`docs/archive/` (pre-build planning/retros, original ideas),
`experiments/archive/` (A–F prototype experiments + their learnings),
`experiments/fly_benchmark/archive/` (earlier findings cohorts).
Everything is also recoverable from git history.

## Layout

- `syngen/` — the package: `pipeline.py` (orchestrator), `phases/` (intake,
  spec, preflight, converge, critic, rework…), `generator/engine.py`,
  `validator/`, `config.py`, `session.py`, `fly.py` (solo-flight harness)
- `packs/revops/` — the RevOps domain pack: checks, signatures, prompts,
  entity schemas, claim matrix
- `scripts/benchmark_fly.py` — fly one/all UAT stories, compute landing rate
- `tests/` — offline suite (FakeLLM drives whole flights deterministically)
- `uat/` — the 25 story scenarios (gitignored, local)

## Common commands

```bash
python -m pytest tests -q          # full suite
python scripts/benchmark_fly.py --stories-dir uat --out experiments/fly_benchmark --offset 0 --limit 1   # fly one scenario
python -m syngen fly "your story"  # interactive solo flight (see syngen/__main__.py)
```

## Status

P6 (realizability gate + missing surfaces) and P7 (flexible stage-rework
loop) are merged to master; the landing-set preservation re-fly ran
**5/5 LANDED** (2026-09-09). Full suite: **379 green**.
