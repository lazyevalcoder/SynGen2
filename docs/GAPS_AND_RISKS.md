# SynGen Gaps, Risks & Anomalies Log

> **Status:** living document. Seeded from the four experiments and the architecture docs. Rule: every anomaly gets a disposition — **fixed**, **accepted** (with reason), or **open** (with owner/trigger). Nothing gets silently dropped.

---

## Open (needs resolution during build)

| # | Gap / Risk | Source | Impact if ignored | Proposed trigger to address |
|---|-----------|--------|-------------------|------------------------------|
| G1 | **Persona critique phase is unvalidated.** Only phase component with no experiment behind it | ARCHITECTURE §4 | Phase 2 may add ceremony without quality; wasted LLM calls | **RESOLVED in M4 (A/B):** no measurable quality benefit across 3 story classes; control arm equal-or-better on iterations and ~35s faster. Personas demoted to opt-in (`--personas` flag, default off); code path retained for unfamiliar domains. See `experiments/M4_persona_ab/` |
| G2 | **Who authors simulator.json initially** — Phase 2 personas or Phase 3 step? Lean Phase 3 seeded by spec | ARCHITECTURE §7 | Blurry responsibility → duplicated logic | Decide at first implementation of Phase 3 |
| G3 | **Knob-proposer context:** explicit transfer function vs learned-from-history. Lean: explicit formula + history refinement | ARCHITECTURE §7 | Agent flails on stacked knobs (D showed greedy fails) | **Largely resolved (M5 iter 1):** playbook of criterion-to-knob mappings + measured margin deltas fed into history. Live lesson F14: playbook must be updated in the same commit as new engine knobs, or the proposer flails on knobs it cannot see |
| G4 | **Thin-margin convergence:** AC5 passed at +0.03pp; seed change could flip it | D learnings | Delivered dataset fails on regeneration | **RETIRED (M5 iter 1):** bounded hardening rounds re-center thin criteria toward mid-band after convergence; failed rounds auto-revert to best known-good state; verified live (m5s23 session) |
| G5 | **No open-pipeline state machine** — original moonshot story (coverage/concentration) needs in-flight deals | DATA_MODEL §4 | Story class unsupported | Engine extension when second story type is attempted |
| G6 | **Single fact table assumption** — multi-fact stories need generation-order awareness | DATA_MODEL §4 | Scope ceiling unknown until story #2 | Defer; revisit at generalization milestone |
| G7 | **Win-rate AC1 at low volume is structurally hard** (binomial noise > band). `exact_count` quota mode exists but changes data character | D learnings | Either noisy failures or slightly artificial determinism | Offer both modes in UX; document tradeoff |
| G8 | **Reasoning-model token budgets** vary by model; hardcoded 8192 worked for Ornith-35B but is a guess | A learnings | Silent empty outputs on other models | **RETIRED (verified M5 iter 1):** client retries empty content with doubled budget capped at max_retry_tokens=16384 (client.py chat loop); json_task escalates ceilings on truncation; covered by test_llm_client budget-escalation tests |
| G9 | **Metric weighting semantics** (simple avg vs revenue-weighted) differ ~1.8pp on AC7-type metrics | D learnings | Criteria pass/fail flips based on unstated choice | contracts doc pins weighting per criterion — enforce at intake |
| G10 | **Criteria dependency propagation** — amending AC3 (Q4 discount) silently invalidates AC7 (realized/list = 100−discount). Discovered in Experiment F | F learnings | Story tweaks score 7/8 with no obvious cause | **RETIRED in M3:** decomposition emits `depends_on` edges; deterministic closure walk (`syngen/phases/amend.py`) surfaces affected dependents at Gate 1 re-approval; live-verified (AC7 declared dependent on AC2+AC3 on first M3 live run) |
| G11 | **Structural story changes untested** — F validated parametric + taxonomy tweaks only | F learnings | Diff classifier may misroute structural edits to the knob loop | **Partially addressed in M3:** classifier + deterministic routing guardrails live (a misrouted parametric proposal is force-escalated to structural); structural escalation message tested. Full validation still needs a real structural story at M4 |
| G12 | **Schema linter coverage is heuristic** — novel pathologies may pass | E learnings | Silent bad specs on unfamiliar domains | **Advanced in M3:** linter ported into package (`syngen/linter.py`), runs as a blocking Gate-1 gate + post-generation structure check; E trap stories in CI (`tests/test_linter.py`). Rule expansion per new domain continues at M4+ |
| G13 | **LLM output flakiness at scale** (live M2 testing): personas truncated mid-JSON ~1-in-2 at a 4096 ceiling; `reasoning_effort` silently ignored by llama.cpp (verified empirically); reasoning burnout burned 16k+ tokens returning empty content; unicode text crashed cp1252 console | M2 live testing | Sessions crash or hang unpredictably on other models/builds | FIXED for current stack: enable_thinking/reasoning_budget_tokens (verified levers), brevity prompts, truncation-aware retries, safe-print. Residual risk: parameter support is MODEL-TEMPLATE dependent — re-probe when swapping models (`scripts/probe_reasoning.py`) |
| G14 | **Knob-proposer can propose non-knob paths** (e.g., editing quarter_end_dates) which patch cleanly but cannot fix calendar-class failures | M2 live run #3 | Wasted iterations chasing structurally impossible fixes | **RETIRED (M5 iter 1):** proposal allowlist enforced at patch time (accounts/opportunities + quota.attainment_by_segment tunable; time_model/seed/output/quota.by_segment blocked); structural check-failures escalate immediately instead of looping |

## Accepted (won't fix, with reasons)

| # | Item | Reason |
|---|------|--------|
| A1 | Denormalized region/segment on facts | Consumer convenience beats normalization for demo data |
| A2 | No slowly-changing dimensions | Quarterly demo horizon doesn't need them |
| A3 | True gross margin unmodelable | Requires cost data we deliberately exclude (A's finding) |
| A4 | xlsx timestamps break byte-determinism | Data-level determinism verified instead (B) |

## Fixed (recorded for posterity)

| # | Anomaly | Fix |
|---|---------|-----|
| F1 | Empty LLM output — reasoning consumed token budget | max_tokens 8192 + capture reasoning_content |
| F2 | Dict iterated without .items() in validator | Code fix + both-direction tests caught it |
| F3 | PowerShell UTF-8 BOM breaks json.load | BOM-free tooling rule in contracts |
| F4 | Relative paths between experiment folders broke validator run | Contracts: absolute paths or run-from-own-dir convention |
| F5 | Windows console cp1252 chokes on unicode punctuation | ASCII-safe CLI output |
| F6 | **Duplicate/synonym tables in generated specs** (opportunities vs deals) — user-reported from prior attempts | Experiment E: strict BI-engineer prompt prevents at source; deterministic linter R1/R5 catches leaks; both layers required |
| F7 | **Stored aggregate tables** (pre-computed metrics as facts) | Experiment E: prompt rule "no pre-aggregated summaries" + linter R2 pattern detection |
| F8 | **Incomplete dimension taxonomies** (story names Enterprise/Mid-Market, world silently loses CSB/SMB) | Experiment E: linter R4 advisory surfaces full real-world taxonomy at Gate 1 as explicit human decision |
| F9 | Linter false positives: plural PK forms, semantic status overlap (Won ⊂ Closed Won), date fields matching status regex | Fixed during E; each is now a linter test case |
| F10 | **Convergence wrote workbooks to `<cwd>/output/` instead of the session folder** — `generate_to_workbook` ignored the session-resolved path; latent since M2, caught when the first M3 live resume showed no `dataset.xlsx` in the session | `converge.py` pins the absolute path into cfg before generating; regression test asserts `<session>/output/dataset.xlsx` exists. Note: append-only `history/` had already rescued a corrupted live session before this was found - section 8 paying off immediately |
| F11 | **Diff classifier proposed corrupting taxonomy edits (two live attempts)** — attempt 1: whole-container replacement with a bare list (crashed the generator); attempt 2: dict replacement that silently RENAMED values (`Enterprise`→`ENT`, `Mid-Market`→`MID`) while adding CSB | Prompt hardened (leaf-path edits only) + deterministic applier rejects list values and any container replacement that drops existing values; three regression tests in `test_session_resume.py`. Lesson: routing guardrails must validate edit CONTENT, not just paths |
| F12 | **Identical-story resume burned an LLM call** and created a redundant story version just to hear "no diff detected" | Short-circuit: identical text routes to regenerate-as-is with zero LLM calls |
| F13 | **Classifier blindspot:** `simulator_summary` hid segment weights, so the classifier refused to propose CSB's share ("re-normalization ambiguous") and improvised instead | Summary now exposes full weight dicts; classifier proposes concrete leaf values |
| F14 | **Knob-proposer playbook lagged engine capabilities** - live #7 run: proposer burned all 5 proposals tuning old knobs because the playbook did not mention medians_by_quarter or icp_sampling_weights_by_quarter (added in the same milestone) | STANDING RULE: any commit that adds an engine knob MUST update the knob_proposal playbook in the same commit |
| F15 | **Proposals into explicit-null config parents dead-ended** ('could not apply: icp_sampling_weights_by_quarter') - get_at_path ran before set_at_path and both choke on None parents | set_at_path replaces null containers; _apply_changes tolerates unreadable 'old' values (old=None) |
| F16 | **Drafter invented quota blocks for vague plan language** ('bookings 3% below plan' with no revenue_vs_plan criterion) - silent raking then overrode deal-size knobs, making the loop chase impossible moves | simulator_draft hard rule: quota only when a revenue_vs_plan criterion exists; knob playbook warns that price knobs are overridden under raking and points at attainment_by_segment (now allowlisted as tunable) |
| F17 | **Drafter draw variance dominates multi-coupling stories** - same #8 story landed 0/4 live attempts; each draft draws different starting configs, and bad starts (>2pp off on 2+ coupled criteria) exhaust the proposal budget. Loop-side fixes (formulas, hill-climbing) all verified working; the bottleneck is upstream | THEME for next pass: deterministic pre-flight calibration between Gate 1 and first generation - verify drafted config against criteria arithmetic before spending iterations |
| F18 | **Proposer lacked coupling transfer functions** - burned rounds tuning margin knobs against realized_vs_list failures (cogs never enters realized/list), never learned count-share vs revenue-share conversion for tier mix | Closed-form formulas added to knob_proposal playbook: blended margin, discount-tier-delta term, rev_share calculus; causal rule that discount-shape checks are immune to products.* knobs |
| F19 | **Schema-plausible patch crashed the generator mid-session** - proposer wrote a per-quarter list into scalar attainment; raking raised TypeError and killed the session | _apply_changes now re-validates the whole patched config and rejects invalid proposals wholesale (restore snapshot); raking tolerates bad ratio types as defense in depth; convergence loop survives generation exceptions by reverting to best partial state |
| F20 | **One-sided share edits rejected whole proposals** - proposer adjusted one product tier's curve, sibling sums drifted outside +/-5%, entire multi-change proposal rejected | Near-miss share sums (~1 +/-0.15) auto-renormalized in _apply_changes (shares are relative weights); gross errors still rejected |
| F21 | **Structure gate false-failed on column ORDER** - expected-sheets contract inserted territory mid-schema while engine appends it last; 'missing=[] unexpected=[]' yet mismatch | expected_sheets_for mirrors engine row-dict insertion order exactly |

---

## Risk Posture

Biggest remaining risk: **G1 (personas)** — everything else has experimental evidence. Second: **generalization** (G5/G6) — we proved one story type; the harness's value claim rests on handling many.

M3 live verification reinforced a meta-lesson: every LLM-authored artifact needs a deterministic validator on its OUTPUT CONTENT, not just its shape — the diff classifier produced schema-valid JSON that was semantically corrupt twice in one session (F11). Mitigation strategy stays the same as it was for experiments 1–4: isolate the risk in a cheap test before building around it.
