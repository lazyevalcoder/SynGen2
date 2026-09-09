# SynGen — Idea v2 (Revised)

> **Note:** This is a revised version of the original `Idea.txt`. The restructuring and recommendations below were suggested by an LLM (Claude) after reviewing the original idea. The core vision remains unchanged; what changed is the sequencing, the emphasis on quantified success criteria, config-driven generation, and a "prove it manually first" experimental path before building any harness.

---

## Intro

This project is called **SynGen**. The purpose is to create high-quality tabular synthetic datasets replicating business scenarios — RevOps, Finance, etc. The use case is to demonstrate BI tools, planning tools, or any other analytical prowess.

The key differentiator: this is **not random data generation**. The user provides a *story*, and the dataset must match the story. Analytics teams tell stories in slides from raw data after much digging — we are doing the reverse. We start with the story and generate the dataset that lands it.

Example story:

> **Pipeline coverage remained healthy at 3.5x, but next-quarter revenue risk increased.** Coverage was concentrated in a small number of large Enterprise opportunities, creating significant dependency on fewer deals. Deal concentration increased forecast volatility even though aggregate coverage looked sufficient. The underlying issue was **pipeline concentration and forecast intelligence**, not simply pipeline quantity.

## Vision

- An agentic harness rather than deterministic software — multiple agents purposed for planning, tool use, memory, and validation.
- The harness is the orchestration engine.
- Think Claude Code, but for synthetic tabular datasets.

**But:** we do not build the harness first. We prove one story end-to-end manually, then automate.

---

## Key Design Changes from v1

1. **Story → Quantified Success Criteria (new, explicit deliverable).**
   A story like "coverage ≈ 3.5x" must be converted into measurable targets with tolerances (e.g., coverage ratio 3.5 ±0.2, top-5 deals ≥ 60% of pipeline value). Without this, the simulation phase has no objective function to converge against.

2. **Config-driven generator over codegen.**
   Schema + distributions live in JSON (`simulator.json`). One fixed, tested Python generator engine interprets the config. LLM-generated code is only a fallback for exotic logic. LLM-written generator scripts break silently; configs don't.

3. **Validation is continuous, not a final phase.**
   Every simulation iteration re-runs validation checks against the success criteria. No eyeballing convergence.

4. **Phases 4 and 5 merged** into a single simulate/validate loop.

---

## Revised Phases

### Phase 1: Story → Intent + Acceptance Targets
- Interpret and decompose the story.
- Capture domain objective, name a persona who works on these problems.
- Capture domain-specific data semantics.
- **Convert the narrative into quantified acceptance targets with tolerances.** This is the objective function for everything downstream.

### Phase 2: Spec Generation
Using Phase 1's output as reasoning input, generate:
- Entities & dimensions
- Relationships
- Measures
- Time model
- Distributions
- Correlations
- Temporal behavior
- Business constraints
- Assumptions
- Validation criteria

Three personas critique/refine the spec:
1. Domain expert (day-to-day practitioner in this context)
2. Business Intelligence engineer
3. Informed outsider (fresh eyes)

The example story never says how many regions, how many quarters, what industry — those gaps get resolved here.

### Phase 3: Config-Driven Generator + Simulator
Three artifacts:
- **Schema definition** (entities, relationships, grain)
- **`simulator.json`** — the constraint/knob engine: distributions, correlations, concentration parameters, temporal rules. Think Anaplan-style parameter tweaking toward base/best/worst cases.
- **One fixed generator script** that reads `simulator.json` and emits the dataset. Not generated per-run — written once, tested once, reused forever.

### Phase 4: Simulate / Validate Loop
Tweak knobs in `simulator.json`, regenerate, re-validate against Phase 1's acceptance targets — until all criteria pass within tolerance. First done manually by a human; later automated by the harness.

---

## Prove It Manually First — Experiments Before Building

The rule: **no orchestration code until every experiment below passes.** Each experiment isolates one risk. If one fails, we learn it cheaply instead of after building a harness.

### Experiment A — Story → Metrics (paper exercise)
- **Do:** Take the pipeline story. By hand (with an LLM prompt at most), produce a list of quantified acceptance criteria with tolerances.
- **Question it answers:** Can a story actually be decomposed into measurable, checkable targets? Where does it get ambiguous?
- **Pass:** A metrics list a script could check without human judgment.
- **Gate:** If we can't quantify the story, nothing downstream works.

### Experiment B — Hand-written simulator.json + minimal generator
- **Do:** Write a ~200-line Python generator plus a hand-authored `simulator.json` for the pipeline story only. Hardcode assumptions (e.g., 4 quarters, 3 regions, 200 opportunities).
- **Question it answers:** Does config-driven generation produce plausible, realistic data?
- **Pass:** Output opens cleanly in a BI tool; distributions look sane on inspection.
- **Gate:** Proves the "fixed engine + JSON knobs" architecture before any agent touches it.

### Experiment C — Validation script
- **Do:** Write a small checker that computes the Experiment A metrics from Experiment B's output and reports pass/fail per criterion.
- **Question it answers:** Do we have a working objective function?
- **Pass:** It correctly fails when data violates a target and passes when it doesn't (test both directions).
- **Gate:** Without this, the simulate loop has no signal.

### Experiment D — Manual convergence
- **Do:** Tweak simulator.json knobs over 5–10 iterations, re-running the validator each time, until all criteria pass.
- **Question it answers:** Is convergence achievable at all? How many knobs are needed? How sensitive is the outcome?
- **Pass:** All criteria green within tolerances.
- **Gate:** If a human can't converge manually, automating it won't help — the concept needs rethinking. If a human can, automating the loop later is straightforward.

### After the gates
Only once A–D pass do we generalize: more story types, persona-based spec critique, and finally the agentic orchestration layer.

---

## Explicitly Deferred (Parking Lot)

- Multi-agent orchestration / harness plumbing
- CLI UX and conversational iteration ("make Q3 worse")
- Multiple story templates and domains beyond RevOps
- Determinism/seed management UI (note the requirement now: seeds must be controllable from day one in the generator)
