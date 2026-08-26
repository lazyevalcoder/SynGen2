# P6 Plan — The Flight Journal ("Hero Journey" Observability)

> **Status:** PLANNED - future enhancement. Vanity/visibility work; the
> program's priority remains unassisted landing rate. Nothing here changes
> flight logic: this is pure instrumentation + rendering.
>
> **Origin:** manager request - "when we give a prompt/scenario, show how
> information traverses the touchpoints/phases and how we get the output."
> Framed as a *hero journey*: the user's prompt is the protagonist; every
> phase, agent, rejection, and fix is a chapter in its story.

## 1. Concept

Tell the story of ONE flight as a narrative with causality, not logs:

- The **hero** is the story (`story.v1.md`) as given by the user.
- It crosses **stages** (precheck, decompose, gates, calibration,
  convergence, delivery) guarded by named **actors**.
- **Allies**: Drafter, Critic, Guard, Auditor, Autopilot (solvers).
- **Trials**: corrective redrafts, consistency lint, geometry lint,
  calibration findings, iteration failures, regression reverts.
- **Reward**: all criteria passing on measured data.
- **Return**: `validation_report.md` delivered - or an honest **death
  scene**: escalation with the named cause and what it would take to
  resurrect.

The reader should answer, from one file: *what happened to MY prompt -
who touched it, what changed, why, what was learned, and how did it end?*

### Campbell mapping (fixed vocabulary for stages)

| Journey stage | SynGen touchpoint | Actor |
|---|---|---|
| Ordinary world | `story.v1.md` saved | - |
| Call to adventure | Precheck claim classification | Prechecker |
| Mentor's gift | User decisions / spec notes | User |
| Drafting the quest | Criteria decomposition | Drafter |
| Threshold guardians | Coverage guard, consistency lint, geometry lint | Guard / Auditor |
| The Critic's verdict | Critic pass A/B (P5 WP9) | Critic |
| Supernatural aid | Deterministic calibration + block synthesis | Autopilot |
| Road of trials | Convergence iterations (scored battles) | Proposer |
| Ordeal & rebirth | Regression reverts, seed bumps, stale-set escalation | Hill-climber |
| Reward | All criteria passing on measured data | Validator |
| Return with the elixir | Gate 2 delivery | Gatekeeper |
| Death in the attempt | Escalation with cause + resurrection path | LoopEscalation |

## 2. Deliverables

1. **`journey_events.jsonl`** (machine trace) - one JSON object per event,
   appended live:

   ```json
   {"seq": 14, "stage": "road_of_trials", "chapter": 6,
    "actor": "Autopilot", "action": "recalibrate",
    "decision": "applied",
    "summary": "solved slippage path (+26pp vs >=12pp)",
    "refs": {"criterion_id": "AC6", "knob_path":
             "pipeline.slippage_rate_by_quarter", "iteration": 3},
    "before": "<digest>", "after": "<digest>", "elapsed_s": 41.2}
   ```

   Refs give full lineage: claim -> criterion -> knob path -> iteration ->
   verdict. Digests are sha1[:8] of the artifact content before/after so
   diffs are addressable without embedding payloads.

2. **`journey.md`** (human narrative) - regenerated on every event, so it
   grows DURING the flight and is complete at the end:

   ```markdown
   # The Flight Journal
   > Hero: "SMB beat plan while mix deteriorated..." (432 chars)
   > Outcome: LANDED - Iteration 2 of 10 - 338s

   ## Spine
   Departure -> Quest drafted (11 criteria) -> Guardian passed (notes x2)
   -> Critic blocked once (redrafted) -> Autopilot solved 6 criteria
   -> Trials: 3 battles, 1 revert -> Reward.

   ## Chapter 1 - The Call (Precheck)
   The story arrived carrying 7 claims. Four were computable...

   ## Chapter 4 - The Guardian
   The first draft reached the Guardian and was turned away twice...
   On the third form the way opened - two claims noted as unknown tongue
   (vocabulary gaps), five passed.
   ```

   Voice: literal storytelling (former per decision) but factually exact -
   every narrative sentence is generated FROM a structured event, never
   LLM-written.

3. **Console stays as-is** - progressive status messages unchanged;
   journey.md is the parallel long-form record.

## 3. Implementation sketch

- New module `syngen/phases/journey.py`:
  - `JourneyRecorder(session)` - `.event(stage, actor, action, ...)` appends
    jsonl + re-renders journey.md; `.chapter(title)` opens a chapter;
    `.finish(outcome)` writes the spine + death-or-return scene.
  - `render_journey(events)` - pure function over the event list (unit-
    testable without flights).
- Emission sites (~18, all existing touchpoints, no new LLM calls):
  session create, story saved, precheck results, decisions captured,
  criteria drafted (n criteria, ids), guard verdict (+gaps), critic A/B
  verdicts (+issues), consistency/geometry lint findings, gate 1 pass,
  simulator drafted (blocks present), calibration findings + fixes,
  autopilot remedies, each iteration (score, passing set, worst margins),
  regression reverts, seed bump, escalation (reason + structural ids),
  convergence + gate 2.
- Wiring: recorder instantiated in `_run_pipeline` / `_converge_and_deliver`
  and threaded where a session already exists. `run_fly` passes nothing new.
- Failure-safety: recorder wrapped fail-open exactly like the critic -
  a journaling crash must never kill a flight.

## 4. Tests (no flights required)

- FakeLLM vertical-slice flight asserts: event ordering matches stage
  sequence, every chapter present, refs carry criterion ids, spine renders,
  escalated flights get a complete death scene, journey.md exists at every
  intermediate assert point (live growth).
- Renderer unit tests: golden markdown snapshot for a canned event list.
- Fail-open test: recorder raising must not affect flight outcome.

## 5. Out of scope (deliberate)

- No dashboards/replay tooling yet (jsonl is the future hook).
- No token/cost accounting per call (telemetry already captures calls;
  can be added to events later).
- No changes to guard/solver/convergence behavior whatsoever.

## 6. Sizing

~1 day: journey.py + renderer (~250 lines), ~18 emission points (1-3 lines
each), tests. Zero risk to landing rate by construction.
