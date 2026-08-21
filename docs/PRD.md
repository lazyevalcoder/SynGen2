# SynGen — Product Requirements Document

> **Status:** v1. Companion docs: `ROADMAP.md` (delivery order), `ARCHITECTURE.md` (how it works), `ARTIFACT_CONTRACTS.md` (interfaces), `../EXPERIMENTS_REPORT.md` (evidence base).

---

## 1. Problem

Analytics teams spend hours digging through raw data to build one credible narrative for a slide, demo, or planning cycle. When they need sample/demo datasets — to showcase BI tools, run planning scenarios, or train analysts — the available options generate **random data that tells no story**. The dataset never matches the narrative; the demo falls flat.

**The reversal SynGen performs:** start from the story, generate the dataset that lands it.

## 2. Target User

- Analytics/BI engineers and RevOps/Finance practitioners preparing demos, planning cycles, or enablement material
- Comfortable with CLI tools and editing JSON
- Single-user, local-first (v1); no server, no accounts

## 3. Product Definition

A conversational CLI harness:

```
user story → quantified acceptance criteria → data spec + simulator.json knobs
          → deterministic multi-table Excel generation → automated validation loop
          → delivered workbook + proof report, replayable and tweakable
```

Not a random-data generator with extra steps: every output must **pass machine-checked acceptance criteria derived from the user's story**, with human gates at criteria sign-off and final delivery.

## 4. Functional Requirements

Each requirement cites its validating experiment.

| ID | Requirement | Evidence |
|----|-------------|----------|
| FR1 | Accept a natural-language business story; pre-check lists claims and flags non-computable ones before decomposition | A |
| FR2 | Decompose story into quantified acceptance criteria (target + tolerance + statistical/parametric classification), resolved with the user at Gate 1 | A |
| FR3 | Critique spec via three personas (domain expert, BI engineer, informed outsider); conflicts surfaced, human decides | G1 — untested, advisory until proven |
| FR4 | Lint every spec: no duplicate grains, no stored aggregates, no dangling FKs, no redundant status fields, taxonomy-completeness advisories | E |
| FR5 | Generate multi-sheet Excel deterministically from `simulator.json` via one fixed engine — zero per-run codegen | B |
| FR6 | Validate workbooks black-box against criteria; emit per-criterion actual/target/tolerance/**margin** and exit code 0/1 | C, D |
| FR7 | Converge automatically: classify failures, propose compensating knob deltas, cap iterations, escalate to human with diagnosis | D |
| FR8 | Persist every project as a session folder; support story tweaks that resolve to config-only changes with identical output structure | F |
| FR9 | Propagate criteria dependencies (`depends_on`) when amendments occur; re-approval required | F |

## 5. Non-Functional Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| NFR1 | Determinism: same seed + same config ⇒ identical data (data-level, not byte-level) | B |
| NFR2 | Excel-native output, multi-sheet, opens in any BI tool | User requirement, day 1 |
| NFR3 | LLM layer is backend-abstracted (OpenAI-compatible); reasoning-model token budgets handled with empty-output retry | A |
| NFR4 | All config/spec files BOM-free UTF-8; ASCII-safe console output on Windows | D |
| NFR5 | Every LLM call, gate decision, and iteration logged to `session_log.md` — sessions fully replayable | AGENT_ROLES |
| NFR6 | Human gates are blocking but minimal: exactly two (criteria sign-off, final delivery) | UX_WIREFRAME |

## 6. Non-Goals (v1)

From ARCHITECTURE §6: no multi-agent orchestration frameworks, no web UI, no second domain until first generalizes, no gross-margin modeling (needs cost data), no BI-tool publishing.

## 7. Success Metrics

| Metric | Target |
|--------|--------|
| Fresh story of a known template lands unattended | ≤10 iterations, ≥80% of attempts |
| Trap-suite lint escapes (E's stories + future additions) | 0 false negatives |
| Story tweak → regenerated dataset | <2 minutes, structure guaranteed identical |
| Validator honesty | 100% catch rate on broken-data suite, 0 false failures on clean data |
| Session replay | Any past session regenerates its exact workbook from history/ |

## 8. Risks & Dependencies

Tracked in `GAPS_AND_RISKS.md` (G1–G12). Top items: persona critique unvalidated (G1), structural story edits untested (G11), linter coverage heuristics (G12). Each roadmap milestone below names the gaps it retires.
