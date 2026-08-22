# SynGen Gaps, Risks & Anomalies Log

> **Status:** living document. Seeded from the four experiments and the architecture docs. Rule: every anomaly gets a disposition — **fixed**, **accepted** (with reason), or **open** (with owner/trigger). Nothing gets silently dropped.

---

## Open (needs resolution during build)

| # | Gap / Risk | Source | Impact if ignored | Proposed trigger to address |
|---|-----------|--------|-------------------|------------------------------|
| G1 | **Persona critique phase is unvalidated.** Only phase component with no experiment behind it | ARCHITECTURE §4 | Phase 2 may add ceremony without quality; wasted LLM calls | First vertical slice: A/B a story's criteria with vs without persona pass |
| G2 | **Who authors simulator.json initially** — Phase 2 personas or Phase 3 step? Lean Phase 3 seeded by spec | ARCHITECTURE §7 | Blurry responsibility → duplicated logic | Decide at first implementation of Phase 3 |
| G3 | **Knob-proposer context:** explicit transfer function vs learned-from-history. Lean: explicit formula + history refinement | ARCHITECTURE §7 | Agent flails on stacked knobs (D showed greedy fails) | Build knob_deltas.json first; measure proposal hit-rate |
| G4 | **Thin-margin convergence:** AC5 passed at +0.03pp; seed change could flip it | D learnings | Delivered dataset fails on regeneration | Loop targets mid-band by default; margin threshold configurable |
| G5 | **No open-pipeline state machine** — original moonshot story (coverage/concentration) needs in-flight deals | DATA_MODEL §4 | Story class unsupported | Engine extension when second story type is attempted |
| G6 | **Single fact table assumption** — multi-fact stories need generation-order awareness | DATA_MODEL §4 | Scope ceiling unknown until story #2 | Defer; revisit at generalization milestone |
| G7 | **Win-rate AC1 at low volume is structurally hard** (binomial noise > band). `exact_count` quota mode exists but changes data character | D learnings | Either noisy failures or slightly artificial determinism | Offer both modes in UX; document tradeoff |
| G8 | **Reasoning-model token budgets** vary by model; hardcoded 8192 worked for Ornith-35B but is a guess | A learnings | Silent empty outputs on other models | LLM layer must detect empty content + auto-retry with larger budget |
| G9 | **Metric weighting semantics** (simple avg vs revenue-weighted) differ ~1.8pp on AC7-type metrics | D learnings | Criteria pass/fail flips based on unstated choice | contracts doc pins weighting per criterion — enforce at intake |
| G10 | **Criteria dependency propagation** — amending AC3 (Q4 discount) silently invalidates AC7 (realized/list = 100−discount). Discovered in Experiment F | F learnings | Story tweaks score 7/8 with no obvious cause | criteria.json gains `depends_on` edges; diff classifier runs consistency check before Gate 1 re-approval |
| G11 | **Structural story changes untested** ("track deals separately from opportunities") — F validated parametric + taxonomy tweaks only | F learnings | Diff classifier may misroute structural edits to the knob loop | Edge-case experiment when session management is built |
| G12 | **Schema linter coverage is heuristic** (name/grain patterns, known taxonomies) — novel pathologies may pass | E learnings | Silent bad specs on unfamiliar domains | Expand rule set per new domain; track lint escapes in this log |
| G13 | **LLM output flakiness at scale** (live M2 testing): personas truncated mid-JSON ~1-in-2 at a 4096 ceiling; `reasoning_effort` silently ignored by llama.cpp (verified empirically); reasoning burnout burned 16k+ tokens returning empty content; unicode text crashed cp1252 console | M2 live testing | Sessions crash or hang unpredictably on other models/builds | FIXED for current stack: enable_thinking/reasoning_budget_tokens (verified levers), brevity prompts, truncation-aware retries, safe-print. Residual risk: parameter support is MODEL-TEMPLATE dependent — re-probe when swapping models (`scripts/probe_reasoning.py`) |
| G14 | **Knob-proposer can propose non-knob paths** (e.g., editing quarter_end_dates) which patch cleanly but cannot fix calendar-class failures | M2 live run #3 | Wasted iterations chasing structurally impossible fixes | Validator now reads calendar from criteria (root cause fixed); consider rejecting proposals touching time_model in the patcher |

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

---

## Risk Posture

Biggest remaining risk: **G1 (personas)** — everything else has experimental evidence. Second: **generalization** (G5/G6) — we proved one story type; the harness's value claim rests on handling many.

Mitigation strategy stays the same as it was for experiments 1–4: isolate the risk in a cheap test before building around it.
