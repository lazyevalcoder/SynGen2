# SynGen — Roadmap

> **Status:** v1. Milestone-based (no dates — solo/asynchronous cadence). Each milestone: scope, exit criteria, and which open gaps (G1–G14 from `GAPS_AND_RISKS.md`) it retires. A milestone is done when its exit criteria pass, not when its code exists.
>
> **V1 completion bar:** v1 is not "done" at M5 — it is done when all 25 narratives in `V1_SCENARIO_REQUIREMENTS.md` land end-to-end. M4/M5 below are the vehicle; the scenario doc is the requirements list and sequencing guide (its workstreams WS1–WS8 slot into M4/M5 as sized).

---

## M1 — Core Engine (library)

**Scope:** The proven experiment code, consolidated into one importable package.
- `generator/` — fixed engine reading `simulator.json` (from B)
- `validator/` — criteria checks + margins + exit codes (from C)
- Contract schemas enforced at load time: `criteria.json`, `simulator.json`, `validation_report.json`
- Test suite: B's determinism/knob tests, C's two-direction suite, D's converged session as a golden test case

**Exit criteria:** Experiments B, C, D flows all reproduce from the package with zero behavior change. Golden-session test green.

**Retires:** nothing yet — this is consolidation, not new ground.

---

## M2 — Vertical Slice (one story type, end-to-end)

**Scope:** Phases 1–4 wired behind the CLI for discount-erosion-class stories.
- Story intake + pre-check + decomposition prompts (FR1, FR2)
- Gate 1 negotiation UX
- simulator.json authoring flow (LLM draft → human approve)
- Convergence loop with iteration cap + escalation (FR7)
- Delivery bundle (workbook + validation report + config)

**Exit criteria:** A *new* user lands a *fresh* story of this class unassisted, first try, in one session. Success metric: ≤10 iterations.

**Retires:** proves the product thesis outside the founder's hands.

---

## M3 — Sessions & Quality Gates

> **Status:** COMPLETE (2026-08-22). Exit criteria verified offline (96 tests) and live: Experiment F's tweak flow replayed entirely through `syngen resume` (taxonomy route landed CSB at target share with original value names preserved); E trap stories covered by `tests/test_linter.py`. G10 retired; G11/G12 advanced (see GAPS log F10–F13 for live-caught defects).

**Scope:** Persistence and hardening.
- Session folder layout per ARTIFACT_CONTRACTS §8; history append-only
- Schema linter integrated at Gate 1 + post-generation (FR4)
- Story-diff classifier: parametric / taxonomy / structural routing (FR8)
- Criteria dependency propagation (`depends_on`) (FR9)

**Exit criteria:** Experiment F's tweak flow works entirely through the CLI; E's trap stories all caught by the linter in CI.

**Retires:** G10 (dependency propagation), partially G12 (linter in CI).

---

## M4 — Generalization

> **Status:** COMPLETE (2026-08-22). Second domain (sales-cycle slowdown) landed iteration 1 live; scenario #6 landed via WS3 raking + revenue_vs_plan (Enterprise 95% / Mid-Market 104% of plan, exact); persona A/B verdict recorded — G1 resolved, personas demoted to opt-in. v1 scorecard: 1 of 25 scenarios LANDED. See `experiments/M4_persona_ab/` and `V1_SCENARIO_REQUIREMENTS.md`.

**Scope:** Prove it's not a one-trick harness, guided by `V1_SCENARIO_REQUIREMENTS.md`.
- Second story domain (candidate: sales-cycle slowdown or renewal/churn — both scoped during experiments)
- Persona critique A/B: criteria quality with vs without persona pass (FR3)
- Scenario-driven workstreams begin: WS3 (aggregate targets/raking), WS1 (planning entity layer: quotas/territories/capacity), WS8 (distribution extensions) — these alone make 11 of the 25 v1 scenarios landable
- Engine extensions only if the second domain demands them beyond that (open-pipeline state machine G5 → WS6, multi-fact ordering G6)

**Exit criteria:** Second domain lands end-to-end via M2's bar; first WS1/WS3-powered scenario lands. Persona A/B verdict recorded — keep, rework, or cut.

**Retires:** G1 (personas), G5/G6 progress (or explicit re-scope), advances G12 (new-domain lint rules).

---

## M5 — Automation & Polish

**Status:** Iteration 3 of 5 complete (2026-08-25). Iter 3: CANONICAL_MODEL adoption, pre-flight calibration gate + auto-calibration suite, P4 open-pipeline state machine. Landings: #8, #18, #20, #11, #5, #21. Scorecard: 10/25 - P4 stories fully landed. Remaining: C/D/E workstreams (capacity/reps, temporal entities, elasticity/mixtures).

**Status:** Iteration 3 of 5 complete (2026-08-24). Iter 3: CANONICAL_MODEL adoption (Option A), pre-flight calibration gate + deterministic auto-calibration suite (F17 theme), P4 open-pipeline state machine (lifecycle stages, expected_close_date, stage-history entity, aging/slippage/coverage/concentration checks). Landings: #8, #18, #20. Scorecard: 7/25. Remaining for P4 stories (#5/#11/#21): empirical stale-distribution correction + coverage-aware plan sizing (F25).

**Status:** Iteration 2 of 5 complete (2026-08-24). Iter 1: convergence intelligence + distribution extensions (#7, #23 landed; #6 earlier). Iter 2: WS2 products/margins, WS4 correlation, WS5 territories + full planning dimension (#12 landed; #3/#8 escalated on drafter variance - F17). Scorecard: 4/25 landed. Iter 3 opens with the drafter pre-flight calibration theme (F17) plus deferred #18/#20 live landings.

**Scope:** Make the loop genuinely hands-off, then complete the scenario surface.
- Knob-delta proposer agent using transfer-function notes + iteration history (G3)
- Margin-aware convergence targeting mid-band by default (G4)
- Packaging: installable CLI, docs site-ready README, prompt library externalized
- Remaining v1 workstreams: WS2 (products), WS4 (correlation), WS6 (open-pipeline state machine), WS7 (temporal entities) — completing all 25 scenarios per `V1_SCENARIO_REQUIREMENTS.md`

**Exit criteria:** All PRD success metrics green AND all 25 scenarios landable end-to-end. Fresh story → landed dataset with zero human touches between Gate 1 and Gate 2 on ≥80% of attempts.

**Retires:** G2, G3, G4, G8 (token-budget auto-retry), G14 (proposal allowlist), remaining G12/G13 items.

---

## Sequencing Logic

```
M1 (trust the engine) → M2 (trust the product) → M3 (trust the replay)
→ M4 (trust the generality) → M5 (trust the automation)
```

Each milestone answers exactly one trust question before the next begins — the same isolation discipline that made the six experiments cheap. If a milestone's exit criteria fail, we stop and diagnose rather than building forward on sand.

## Explicitly Deferred

Web UI, multi-user/server mode, BI-tool integrations, additional domains beyond M4's scope, orchestration frameworks. Revisit only after M5.

## Post-v1 — Domain Packs (unscheduled)

**Trigger:** any requirement to generate synthetic data for a second vertical (e.g., finance/accounting/treasury scenarios). No timeline committed; do not start before v1 ships.

The harness (loop, raking, sessions, guardrails, playbook learning) is domain-agnostic and proven across three story classes. What is RevOps-specific today: the engine table schemas (`accounts`/`opportunities`), the 13-check sales-metric library, and the analyst persona in prompts. A domain pack is the swappable surface:

1. **Prompt profiles** — per-domain persona + data-model description (decompose/draft/precheck)
2. **Fact generators** — new entities behind the same declarative config (`invoices`, `cashflows`, `gl_entries`...); generic primitives (period curves, raking vs budget, mix-shift, outliers) carry over untouched
3. **Check pack** — domain metrics as registered checks following the margin contract (~30 lines each; e.g., DSO trend, aging buckets, liquidity ratios)
4. **Lint taxonomies** — entity vocabularies for the new tables

Cost estimate: first new domain ≈ M1–M3 effort; subsequent domains are fractions of that. Design constraint to honor during M5 phases 2–5: avoid baking additional sales assumptions into shared schemas (products/temporal entities should stay pack-neutral where cheap).
