# SynGen Agent & Component Roles

> **Status:** v1 draft. Who does what, per phase. The recurring question for every task: **is intelligence actually needed here?** Experiment B proved the most reliable component was the one with zero LLM involvement.

---

## Role Legend

- 🤖 **LLM call** — language reasoning; prompt + response logged to the session's prompt log
- ⚙️ **Deterministic code** — permanent, tested engine code
- 🧑 **Human gate** — owner judgment; harness waits

---

## Phase 1 — Decompose

| Task | Actor | Notes |
|------|-------|-------|
| Story intake pre-check | 🤖 | List claims, flag non-computable ones *before* full decomposition (A's cost-data catch) |
| Claim → criteria draft | 🤖 | Prompt library entry P1 (from `prompts_log.md`); budget `max_tokens ≥ 8192` for reasoning models |
| Ambiguity listing | 🤖 | Every under-specified term surfaced with a proposed resolution |
| Criteria sign-off | 🧑 | **Gate 1.** Owner edits targets/tolerances/resolutions |
| criteria.json emission | ⚙️ | Rendered from approved review, never hand-typed |

## Phase 2 — Spec

| Task | Actor | Notes |
|------|-------|-------|
| Persona: domain expert critique | 🤖 | "What would a RevOps practitioner challenge in this spec?" |
| Persona: BI engineer critique | 🤖 | Grain, joins, aggregability, tool-consumability |
| Persona: informed outsider critique | 🤖 | Fresh-eyes ambiguity hunt |
| Conflict resolution | 🧑 | Personas run in parallel; dissent recorded in spec.md, human decides |
| Assumption→knob mapping check | ⚙️ | No orphan assumptions (contract rule) |
| Schema lint of spec draft | ⚙️ | R1–R5 rules (DATA_MODEL §5); R4 taxonomy advisories surface here as human decisions — the CSB-class catch (Experiment E) |

**Note:** personas are the ONLY phase component not yet validated by an experiment. Treat its output as advisory until proven. The deterministic schema linter (also E-validated) is the hard guarantee behind them.

## Phase 3 — Generate

| Task | Actor | Notes |
|------|-------|-------|
| simulator.json authoring | 🤖 draft → 🧑 approve | LLM drafts knobs from spec; human approves because knobs are business decisions |
| Dataset generation | ⚙️ | Fixed engine. Seeded. Never regenerated as code. |
| Summary sheet computation | ⚙️ | Derived from facts at write time |

## Phase 4 — Converge

| Task | Actor | Notes |
|------|-------|-------|
| Validation run | ⚙️ | Black-box vs workbook; emits validation_report.json with margins |
| Failure classification | ⚙️ first, 🤖 fallback | statistical/parametric tag already on each criterion (Phase 1); LLM only re-classifies when tagged strategy fails twice |
| Knob-delta proposal | 🤖 | Reads validator table + margins + transfer-function notes; emits knob_deltas.json with predicted effects + compensation links |
| Delta application | ⚙️ | JSON-path patch to simulator.json; config hash logged |
| Iteration cap escalation | 🧑 | After N failed iterations (default 10), harness presents diagnosis instead of continuing |
| Story-diff classification | ⚙️ + 🤖 | On story edit: parametric → Phase 4 only; taxonomy addition → config edit; structural → Phase 2 revisit. Must propagate criteria `depends_on` amendments before Gate 1 re-approval (Experiment F) |
| Final inspection | 🧑 | **Gate 2.** Human opens workbook before delivery |

---

## The Orchestrator

Not an intelligent agent — a deterministic state machine:

```
INTAKE → PRECHECK → DECOMPOSE → GATE1 → SPEC → GENERATE_SETUP
      → [GENERATE → VALIDATE → PROPOSE → PATCH]* → GATE2 → DELIVER
```

It routes artifacts between components, enforces gates, caps loops, and writes the session log. If it ever needs "judgment," that's a design smell — push the judgment into a named role above.

**Rationale:** Idea_v2's own warning — don't build orchestration before proving the loop manually. We proved it; the orchestrator is just the loop we ran by hand, encoded.

---

## Session Log (memory)

Every LLM call, gate decision, iteration, and artifact hash appends to `session_log.md`:
- prompt + response (or reference if large)
- gate decisions with who/when
- per-iteration: config hash, report hash, deltas applied

This is the harness's memory. It makes any session replayable and is what an agent reads to avoid repeating failed knob moves across sessions.
