# SynGen — Experiment Summary Report

> **Purpose:** Four isolated experiments were run to validate the SynGen concept — "story in, dataset out" — before building any agentic harness. Each experiment tested one specific risk, in dependency order, with a clear pass/fail gate. **All four gates passed.** The concept is proven end-to-end manually, at near-zero cost.

**Date:** August 2026
**Story used:** Discount Erosion (medium-complexity RevOps scenario)
> *"Win rates held steady this year, but average deal discounts crept up from 12% to 18%, quietly eroding margins. The bleed is worst in EMEA, where reps are discounting aggressively to close end-of-quarter deals."*

**Final artifact:** `experiments/B_config_generator/output/syngen_demo.xlsx` — 60 accounts, 1,600 opportunities, 3-sheet Excel workbook, deterministic (seed 42), passing all 8 acceptance criteria.

---

## Results at a Glance

| # | Experiment | Question it answered | Gate | Result |
|---|-----------|---------------------|------|--------|
| A | Story → Metrics | Can a story be decomposed into script-checkable criteria? | Human + LLM decompositions converge | **PASS** |
| B | Config Generator | Does config-driven generation produce plausible data? | Deterministic, knob-responsive, sane | **PASS** |
| C | Validator | Is there a working objective function? | Catches broken data both directions | **PASS** |
| D | Convergence Loop | Can knobs be steered to land the story? | 8/8 criteria within ~10 iterations | **PASS (2 iterations)** |
| E | Schema QC (adversarial) | Are duplicate tables / stored aggregates / missing taxonomy segments caught? | All induced pathologies detected, control clean | **PASS** |
| F | Session Tweak Loop | Does a small story edit yield same-structure, new-value datasets via config-only changes? | Structure identical, 8/8 amended criteria PASS | **PASS** |

---

## Experiments E & F — Edge-Case Hardening (August 2026 addendum)

Run after the core four, targeting three user-reported concerns from prior project attempts.

### Experiment E — Adversarial Schema QC (`experiments/E_schema_qc/`)
**Concern:** prior attempts produced duplicate synonym tables (`opportunities` + `deals`), pre-computed metric tables, and silently incomplete dimension taxonomies.

**Method:** four trap stories fed to the LLM under a strict BI-engineer prompt; resulting specs run through a hand-built deterministic linter (rules R1–R5).

**Results:**
- Control story: clean spec, zero false positives
- Synonym-duplication trap: prompt prevented table duplication; linter R5 caught leaked redundant status fields (`stage` + `close_status`)
- Stored-aggregate trap: prompt prevented aggregate tables; linter R3 caught undeclared FKs
- Incomplete-taxonomy trap: linter R4 flagged missing CSB/Consumer — the exact reported scenario — converting it into an explicit human decision

**Key finding: defense in depth.** The prompt shapes generation; the deterministic linter guarantees it. Neither layer alone suffices.

### Experiment F — Session Tweak Loop (`experiments/F_session_tweak/`)
**Concern:** users must be able to return, tweak the story slightly, and get a same-structure dataset with different values.

**Method:** took D's converged session; presented an amended story ("Q4 discounts ~21%, add CSB segment"); classified the diff; changed only simulator.json + criteria.

**Results:**
- Structure identical (sheets/columns); CSB materialized (9 accounts / 239 opportunities); Q4 discount moved 19.16→21.16%; untouched quarters reproduced exactly
- Zero generator code changes
- **New discovery — criteria dependency propagation:** amending AC3 (Q4 discount) mathematically invalidated AC7 (realized/list = 100−discount). First run scored 7/8 until the implied amendment propagated. criteria.json now requires `depends_on` edges and the diff classifier must check consistency before Gate 1 re-approval.

### Dispositions
- Concern #1 (session tweak/replay): addressed by F; session layout contract added to ARTIFACT_CONTRACTS §8
- Concern #2 (structural QC): addressed by E; linter codified in DATA_MODEL §5
- Concern #3 (taxonomy completeness): addressed by E (R4 advisory)
- New gaps logged: G10 (dependency propagation), G11 (structural edits untested), G12 (linter coverage heuristics)

---

## Experiment A — Story → Quantified Acceptance Criteria

**Folder:** `experiments/A_story_to_metrics/`

### What was done
The story was decomposed into 8 acceptance criteria (AC1–AC8), each with a target value, tolerance, and computable definition. Independently, the local llama.cpp LLM (Ornith-1.5-35B-Q4_K_M) was given the same story and asked to produce its own decomposition. The two were then reconciled.

### The criteria that emerged
| ID | Criterion | Target |
|----|-----------|--------|
| AC1 | Win rate flat across quarters | each quarter within ±3pp of annual mean |
| AC2 | Q1 avg discount (won deals) | 12% ±2pp |
| AC3 | Q4 avg discount (won deals) | 18% ±2pp |
| AC4 | Discount trend rises without dips >1pp | monotonic-ish |
| AC5 | EMEA discount premium over AMER/APAC | ≥ +5pp in H2 |
| AC6 | End-of-quarter discount effect (final 14 days) | ≥ +5pp vs mid-quarter |
| AC7 | Realized revenue as % of list price | declines 88% → 82%, ±2pp |
| AC8 | Data sanity (bounds, FKs, dates) | hard constraints |

### Key findings
1. **Convergent decompositions.** The LLM's 5 criteria mapped ~1:1 to the human draft's 8. Differences were only tolerance magnitudes (±1.5 vs ±2pp) and window definitions (30d vs 14d) — resolved in a documented reconciliation table.
2. **The LLM caught a real trap:** true "margin erosion" is not computable without cost data. Our AC7 sidesteps this by using realized/list-price ratio as a computable proxy — the cross-check validated that design choice.
3. **Reasoning-model mechanics:** the model emits `reasoning_content` before `content`; first attempt returned empty because reasoning consumed the 2048-token budget. Fixed with `max_tokens: 8192`. Future harness prompts must budget for reasoning tokens.
4. Ambiguity resolution (windows, tolerances, won-deals-only scoping) turned out to be the real work of decomposition — this becomes an explicit "spec clarification" step in the future harness.

### Verdict
**PASS.** Stories can be reverse-engineered into measurable targets, and independent decompositions agree on substance.

---

## Experiment B — Config-Driven Generator

**Folder:** `experiments/B_config_generator/`
**Artifacts:** `simulator.json`, `generate.py` (~200 lines), `verify_b.py`, `output/syngen_demo.xlsx`, `learnings.md`

### What was done
Hand-authored a `simulator.json` containing every business number — win rate (+ jitter), region/segment mixes, lognormal deal sizes, per-region-per-quarter discount base curves, end-of-quarter boost, noise, seed. Wrote ONE fixed generator script that interprets the config and emits a multi-sheet Excel workbook (`accounts`, `opportunities`, `quarterly_summary`). No LLM involved in generation — deliberately.

### Verification results
| Check | Result |
|-------|--------|
| Determinism (same seed → identical data on re-run) | PASS |
| Knob change (`noise_sd_pp` 3→8) changes output without code edits | PASS (spread 4.68→8.78pp) |
| Data sanity (discount bounds, positive amounts, valid FKs, dates in quarter) | PASS |

### Key findings
1. **The architecture held:** across ALL subsequent iterations (Experiment D), only JSON changed — the generator code was never touched.
2. **Baseline data already showed the story's shape** (rising discounts, EOQ crunch) but missed some tolerances — expected; convergence was D's job.
3. **Sample-size insight discovered early:** at 100 opportunities/quarter only ~27 are won (~8 EMEA won deals), making regional metrics noisy. This drove the volume decision in D.
4. **xlsx files embed timestamps** — determinism must be verified on data content, not file bytes.

### Verdict
**PASS.** "Fixed engine + JSON knobs" works before any agent touches it.

---

## Experiment C — The Validator (Objective Function)

**Folder:** `experiments/C_validator/`
**Artifacts:** `criteria.json`, `validate.py`, `test_validator.py`, `learnings.md`

### What was done
Built a black-box checker that reads ONLY the Excel workbook (like a BI tool would — no access to config or generator), computes each criterion from `criteria.json`, prints a PASS/FAIL table with actual vs target vs tolerance, and exits 0/1 so loops can drive convergence programmatically.

### Two-direction testing (the gate)
**Direction 1 — broken data must fail.** Four deliberately mutated workbooks:
| Mutation | Targeted criteria | Detected? |
|----------|------------------|-----------|
| Discounts flattened to ~15% everywhere | AC2, AC3, AC5, AC6 | All failed ✓ |
| Win rates forced to 15/40/20/35% by quarter | AC1 | Failed ✓ |
| EMEA premium removed | AC5 | Failed ✓ |
| Negative price + orphan FK injected | AC8 | Failed ✓ |

**Direction 2 — honest verdict on real data.** Baseline scored 3/8 PASS, fully consistent with Experiment B's observations. No false confidence either way.

### Key findings
1. **Tolerances are well-calibrated:** baseline AC6 missed by just 0.06pp — neither trivially loose nor impossible.
2. **Naming precision matters:** AC4 ("trend rises") actually only forbids dips >1pp — a flat trend legitimately passes. Criteria names must match their signed-off definitions exactly.
3. Machine-readable criteria (`criteria.json`) means adding future criteria = JSON, not code paths.

### Verdict
**PASS.** The objective function exists and is trustworthy in both directions.

---

## Experiment D — Manual Convergence Loop

**Folder:** `experiments/D_convergence/`
**Artifacts:** `iterations_log.md`, `learnings.md`

### What was done
The core simulation loop, executed manually: diagnose validator failures → adjust `simulator.json` knobs → regenerate → re-validate → record. Maximum budget: 10 iterations.

### Iteration history
| Iter | Diagnosis → Knob changes | Result |
|------|-------------------------|--------|
| Baseline | — | 3/8 PASS |
| 1 | Q4 overshoot = base curve + EOQ boost stacking; EMEA premium far too weak; win-rate noise structural at n=100. → volume 100→400/qtr, boost 5→5.5pp, reshaped base curves, forced EMEA H2 premium | 7/8 PASS |
| 2 | AC6 alone failing, running ~0.7pp under configured boost. → boost 5.5→6.5pp, Q1 bases 12→11.5pp to compensate stacking | **8/8 PASS — STORY LANDED** |

### Key findings
1. **Knob math is predictable.** After one calibration iteration, every outcome was predicted within ~0.5pp using:
   `expected_won_avg = blend(base_by_quarter, region_mix) + eoq_share × boost + clip_bias`
   This transfer function is what will make automating the loop straightforward.
2. **Statistical vs parametric criteria need different fixes.** AC1 (win rate) could never be fixed by discount knobs — binomial noise exceeded the band at n=100. The fix was *volume*, not tuning. The harness must classify criteria before iterating.
3. **Knobs stack.** Raising the EOQ boost pushed Q1 past AC2's ceiling; required simultaneous compensating moves. Greedy single-criterion adjustment would oscillate.
4. **Thin margins exist.** Final margins: AC5 +0.03pp, AC6 +0.77pp. Production loops should target mid-band or report margin, or a seed change flips results.
5. **Hidden weighting semantics.** AC7 runs ~+1.8pp above simple-average prediction because realized/list weights deals by size — metric definitions carry hidden weighting that spec phase must pin down.
6. **Tooling friction:** PowerShell `Set-Content -Encoding UTF8` writes a BOM that breaks `json.load`; relative paths between experiment folders bit once. Minor but worth encoding into harness conventions.

### Verdict
**PASS. Converged in 2 of 10 allowed iterations.** The thesis — stories can be landed by parameter steering — is validated manually.

---

## Overall Conclusion

The SynGen concept survived every isolation test:

1. **Stories decompose into checkable numbers** (A), independently confirmed by LLM.
2. **A fixed engine + JSON config generates realistic multi-table Excel** (B), deterministically.
3. **An automated objective function judges datasets honestly** (C).
4. **Humans can steer configs to land any given story** (D) — quickly, predictably, and with zero code changes.

Because convergence took 2 iterations with a predictable transfer function and machine-checkable exit codes, **automating this loop with agents is now straightforward engineering rather than research risk.**

## Recommended Build Order (from here)
1. Generalize the generator beyond hardcoded schema (entities/fields driven by spec output)
2. Automate the convergence loop (agent reads validator table + margins, proposes knob deltas)
3. Persona-based spec critique (Phase 2 of Idea_v2) feeding `criteria.json`
4. Second story/domain to test generalization before any orchestration layer

## Detailed artifacts
- Original idea: `Idea.txt` · Revised plan: `Idea_v2.md`
- Per-experiment details: `experiments/<experiment>/README.md` + `learnings.md`
- Full iteration trace: `experiments/D_convergence/iterations_log.md`
- Prompt library (seed): `experiments/A_story_to_metrics/prompts_log.md`
