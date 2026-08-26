# SynGen Domain Packs — Design of Record

*Written 2026-08-25. Decided after the fly-benchmark Pass-1 evidence (7/25
flights, see `experiments/fly_benchmark/FINDINGS.md`): 6 of 6 non-landings
died in the intake/coverage-guard layer, and the root cause was structural —
fuzzy-text coverage judgment with no canonical claim representation. This
document is the design of record for the Domain Packs workstream, promoted
from "Post-v1, unscheduled" to active milestone M6.*

## Decisions (2026-08-25)

1. **RevOps only for v0.** No second pack is built or scaffolded. The
   architecture must be general; the codebase stays single-domain.
2. **Single pack per session.** A session binds to exactly one pack at
   intake. Pack blending is explicitly out of scope.
3. **Name:** "domain-packs". The pack manifest is normative ("the bible"):
   every layer either derives from it or validates against it.
4. **Multi-agent drafter/critic split ships inside v0** (user decision:
   "if it fixes and doesn't break things"). It lands behind the same
   golden-anchor discipline as everything else.
5. **Fly benchmark Pass-1 frozen at 7/25** as the baseline-as-built.
   Remaining flights are not run under the old guard; all 25 stories re-fly
   as the pack-v0 certification suite.

## The problem this solves

The benchmark isolated one dominant failure family (`criteria-quality /
guard-policy`: findings F5.1, F7.1, F9.1, plus vocabulary holes F5.2, F6.1,
F7.2, F9.2, F10.2). Its root cause: the coverage guard asks an LLM to
compare free-text claims against free-text criteria parameters and judge
equivalence. Fuzzy-vs-fuzzy matching has no stable correct answer, so the
guard is simultaneously too strict (rejects equivalent coverage) and too
loose where it matters (hallucinates check names when vocabulary runs out).

Secondary debt: RevOps semantics are duplicated across engine blocks, 33
checks, solver algebras, prompt prose, linter rules, autopilot recipes,
profiles, and test fixtures. decompose.txt omitting iter-4 checks caused
real failures until manually patched. Hand-maintained duplicates drift;
generated catalogs cannot.

## What "the bible" means operationally

The pack manifest is the **single source of truth from which every layer is
derived or validated**:

- Prompt catalogs (decompose / draft / simulate / audit check lists) are
  **generated from** the registry — never hand-maintained alongside it.
- The linter's known-block/entity vocabularies are derived from pack
  entities.
- Configs, criteria, and session state validate against the pack at load
  time; unknown references are hard errors.
- Coverage decisions are set algebra over matrix cells (below), not
  judgment calls.

## Kernel vs pack boundary

Rule of thumb: **if it mentions quota, win rate, or stage, it is pack. If
it would work identically for headcount planning, it is kernel.**

| Kernel (domain-neutral) | Pack (RevOps in v0) |
|---|---|
| Session store, gates, convergence loop | Entity schemas (accounts, opportunities, quota_plan, reps, capacity_plan, account_ownership, account_activity, forecast_snapshot, opportunity_stage_history) |
| Autopilot scheduler + remedies | Claim taxonomy (matrix cells + cohort algebra) |
| Validation runner, fly harness | Check library (proof procedures) |
| Raking, mixture/outlier/trend/state-machine primitives | Calibration solvers |
| LLM client, case-memory infra | Autopilot recipes, prompt fragments, few-shot examples, UAT certification suite |

## Pack anatomy

Two locations, by artifact kind (decided in P3):

- **Declarative artifacts** — repo-root `packs/revops/`: `pack.json`,
  `claims/matrix.json`, `prompts/*.txt` (domain prompt fragments).
- **Python plugin code** — `syngen/packs/revops/`: importable
  implementations (the check library lives here since P3; it is the single
  source of truth, with `syngen/validator/checks.py` as a compat shim).

Target layout (later phases complete the move):

```
packs/revops/
  pack.json              # identity, version, kernel-compat pin
  entities/*.json        # canonical schemas (pending expert sign-off)
  claims/matrix.json     # THE coverage matrix (+ per-check vocab docs)
  prompts/*.txt          # semantic fragments injected per kernel phase
syngen/packs/revops/
  checks.py              # proof procedures (moved P3)
  solvers.py             # calibration algebras (deferred - see below)
  recipes.py             # autopilot templates (deferred - see below)
  examples/              # landed configs -> few-shot / retrieval (future)
```

Checks and solvers are Python plugins behind stable interfaces now; a DSL
is considered later only if a demonstrated need appears.

## The claim matrix (centerpiece)

Canonical claim shape:

```
claim = { entity, metric, cohort, direction, magnitude?, period? }
```

- `entity`: revenue | pipeline | commit | capacity | ownership | activity | forecast | ...
- `metric`: level | trend | share | ratio | divergence | concentration | ...
- `cohort`: named composable filter (all, ex_outlier, early_stage,
  top_value, inactive_stalled, new_territory, ...)

The matrix maps each cell to capabilities `{generator, solver, check}`.
Cell states and their meanings:

| Cell state | Meaning | Action |
|---|---|---|
| generator + solver + check | fully served | fly |
| check but no solver | expressible, hard to calibrate | LLM-proposes; guard watches |
| no check | vocabulary gap | auto-classified VOCAB-GAP -> roadmap queue file; never flight-fatal |

Benchmark mapping (why this works): F5.1/F7.1/F9.1 pedantry disappears
(equivalent cells match exactly); F10.1-style direction inversions are
caught mechanically via the `direction` field (the one true save survives);
vocabulary holes become clean roadmap signals instead of flight failures.

## Graduated guard policy

The guard's response graduates instead of binary pass/escalate:

1. `PROCEED` — all claimed cells served.
2. `PROCEED-WITH-NOTE` — partial gaps that are narrative qualifiers or
   declared caveats; note lands in criteria/report.
3. `REDRAFT` (bounded) — parametric/directional fixes (wrong direction,
   wrong parameter shape); drafter gets targeted feedback.
4. `ESCALATE` — near-zero coverage only.

Auditor contract: every gap report must either **name an EXISTING check**
or classify the claim as **VOCAB-GAP**. Invented check names are invalid
output (kills the hallucinated-suggestion failure).

## Multi-agent roles (inside v0)

Same-model, incentive-separated roles — not "more opinions" (the M4 persona
A/B showed same-incentive critique adds nothing):

1. **Drafter vs adversarial critic** (Gate 1): drafter maximizes defensible
   coverage; critic attack-pass tries to construct counterexample datasets
   passing all criteria while violating a claim. Successful attacks = real
   gaps; failed attacks close the complaint.
2. **Blind re-decomposer**: independent decomposition without seeing the
   drafter's criteria; diff = disagreement signal for systematic blind spots.
3. **Verification-before-delivery** (Gate 2): fresh-context agent reads only
   story + validation report and answers "does this proof demonstrate the
   story?" — catches vacuous passes.

Rationing: roles 1–2 at Gate 1 only, role 3 once per flight (local endpoint,
minutes per pass — spend only at asymmetric-consequence decisions).

## Migration plan (distill, don't rewrite)

Golden-anchor byte-identical reproduction tests gate every phase.

| Phase | Content |
|---|---|
| P0 ✅ | Spec + kernel plugin interfaces; pack skeleton + manifest; loader with import-time validation and drift tripwires. Zero behavior change. |
| P1 ✅ | Claim matrix (33 cells, one per check, KPI-bound, with vocab docs); cohort algebra (`syngen/packs/cohorts.py`); `PackTaxonomy` adapter; **graduated guard** (PROCEED → PROCEED-WITH-NOTE → REDRAFT bounded → ESCALATE near-zero/impossible-math only); auditor PARAMETRIC/VOCAB_GAP/QUALIFIER contract with existing-check naming. |
| P2 ✅ | Generated catalogs: decompose/coverage_audit prompts render `{{check_catalog}}`/`{{check_names}}` from the matrix - hand-maintained prompt check lists deleted. |
| P3 ✅ | Check library moved into `syngen/packs/revops/checks.py` (kernel shim keeps legacy imports); prompt fragments moved to `packs/revops/prompts/`; F8.1 sigma-less hardening (schema contract + deterministic 0.6 default in preflight); F8.2 crash-path session inference in fly reports; F5.3 rejected criteria persisted on guard escalation. |
| P3.5 ✅ | Entity schemas machine-readable: `packs/revops/entities/*.json` (10 artifacts) transcribed from ENTITY_SCHEMA.md; loader loads + structurally validates them; tripwires: matrix cells ↔ schema links, generated workbook headers == schema contract, all 25 UAT scenario block refs expressible + criteria checks pack-declared. |
| P4 ✅* | Certification flown 10/25 (paused at mid-run synthesis, findings_v2.md): 2 landed, 7 escalated, 1 crashed; landing rate 20% vs 14.3% baseline; ZERO guard deaths (M6 guard thesis confirmed). Failure taxonomy saturated on ONE family: coordinate scoping/feasibility unvalidated at Gate 1. Remaining 15 flights deferred until after P5. |
| P5 ✅ | **Flight-control envelope** - class-level fixes for every certification failure family: WP1 coordinate signature registry (`check_signatures.json`, 33 checks, loader-validated); WP2 Gate-1 criteria consistency lint + bounded corrective redraft (F15.2/F18.2); WP3 criteria×config geometry cross-lint post-calibration (F11.x/F18.3); WP4 solver discipline - phantom-solve preconditions, scoped-first unit ledger, uniform capacity synthesis (F11.1/F15.1/F14.1); WP5 input hardening ConfigError everywhere (F12.1/F18.4); WP6 raking-economics feasibility check (F13.2); WP7 proposer knowledge injection from signatures (F16.1/F17.1/F15.3); WP8 normalized scoring + stale-passing-set escalation (F13.4/F17.2); WP9 multi-agent critic shipped - two verification points (post-criteria, post-config), block verdicts trigger one corrective redraft each, fails open on critic failure. Regression tests replay every failure family (test_p5_envelope.py). |
| P6 ⏳ | **Realizability gate + missing surfaces** (branch `fix/realizability`, 3 commits) - the "criteria signed that the generator cannot truthfully construct" class (findings_v3.md F19.x). Part 1 (gate): unknown/hallucinated check names ⇒ hard finding + bounded redraft (F19.8); engine defaults `accounts.segments` when absent (F19.7); geometry lint gets one corrective criteria re-draft with expressible-form hints before escalating (F19.6); tier revenue-share targets above the arithmetic ceiling flagged infeasible (F19.3). Part 2 (surfaces): capacity synthesis rises headcount flow when `headcount_growth_placement` required + converge remedy concentrates additions into measured-strong units before the structural check (F19.10); elasticity_differential solver sets price path/elasticity + deal-count floor to land the gap deterministically (F19.9/AC6); `quota_vs_potential` cohort expressions (`top_pct`/`bottom_pct`) supported in check+signature+remedy (F19.6, kills s15/s18 subset claims). Part 3 (honesty net): calibration-agreement sweep test - every closed-form solver run against a real workbook across 3 seeds (drift gate); deal-count floor for noise-sensitive margin/share/elasticity checks (F19.2); margin noise-floor lint note (~4pp tail). All rules are general (keyed to check names/config shapes, zero scenario conditionals). Suite 372 green. Verification: fresh cohort 21-25 is the real test (never examined); landing set 05/09/11/13/14 preservation is a regression check. Record: `findings_v4.md`. |


### Deferred within P3 (documented decision)

- **Solver extraction from preflight**: `_autocalibrate_*` families are
  RevOps algebra entangled with kernel findings machinery (~1500 lines,
  heavily byte-identical-tested). Splitting without risking golden-anchor
  violations is its own project; scheduled post-certification.
- **Recipe extraction** (converge.py remedies): same entanglement rationale.
- **entities/\*.json transcription**: awaits the expert-reviewed
  ENTITY_SCHEMA.md column schemas (user hand-writes them).

## Success criteria for M6 / v0

1. Full test suite green throughout; golden anchors byte-identical at every
   phase gate.
2. Certification re-fly: unassisted landing rate materially above the
   14.3% baseline; zero flights killed by qualifier pedantry; every
   escalation names a real gap; every vocabulary hole lands in the roadmap
   queue rather than failing a flight.
3. All RevOps semantics live in exactly one place (the pack), provable by
   grep-audit for duplicated catalogs.

## Relation to existing documents

- `CANONICAL_MODEL.md` remains the entity-schema source of truth; its
  entities become `packs/revops/entities/*.json`.
- `FLIGHT_MODEL.md` doctrine unchanged; domain-packs implements its
  "maintenance loop" layer structurally.
- `ROADMAP.md` M6 supersedes "Post-v1 — Domain Packs (unscheduled)".
