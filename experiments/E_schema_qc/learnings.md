# Experiment E — Learnings

## Result: GATE PASS — all three pathologies caught, control clean

## Setup
Four stories sent to the LLM (Ornith-1.5-35B) with a strict BI-engineer system prompt ("minimal tables, no pre-aggregated summaries, use real-world taxonomies"). Draft specs then run through a deterministic 5-rule linter (`schema_linter.py`).

## Results
| Story | Pathology induced | LLM prompt layer | Linter layer |
|-------|------------------|------------------|--------------|
| CONTROL (discount erosion) | — | clean spec | clean ✓ |
| T1 synonym duplication | opportunities + deals dup tables | **prevented** (merged into one entity) | R5 caught what slipped through: redundant `stage` + `close_status` fields |
| T2 stored aggregate | quarterly_metrics as stored table | **prevented** (no aggregate tables) | R3 caught undeclared FKs (`quarter_id`, `region_id` with `references: null`) |
| T3 incomplete taxonomy | only Enterprise/Mid-Market world | partially resisted (added SMB) | R4 flagged missing CSB/Consumer — exactly the user's scenario |

## Key findings

### 1. Defense in depth is required and works
The strict system prompt prevented the two worst structural pathologies *before* they existed. But prompts are probabilistic — the deterministic linter caught every issue that still leaked (redundant status fields, dangling FKs, taxonomy gaps). **Neither layer alone is sufficient: prompt shapes generation; linter guarantees it.**

### 2. The user's CSB scenario is real and reproducible
T3's story named two segments; the LLM generated three (added SMB unprompted — good instinct) but still missed CSB. R4's advisory ("real-world taxonomy likely includes CSB/Consumer — include unless story excludes") converts a silent data-quality bug into an explicit human decision at Gate 1.

### 3. Linter rules earned during this experiment (now test cases)
- Primary keys come in plural/singular forms (`accounts` → `account_id`) — PK exemption must check both
- Status-field redundancy is semantic (`Won` ⊂ `Closed Won`), not literal — needs token-level overlap
- Date-typed fields must be excluded from status-semantics matching (`close_date` ≠ status)
- Canonical value sets (AMER/EMEA/APAC) need whitelisting or R4 cries wolf

### 4. Architecture placement
Linter runs at **Gate 1** (on Phase 2 spec output) and again post-generation on actual workbook schema. It is deterministic code in AGENT_ROLES terms — never an LLM judgment.

## Disposition of original concerns
- User concern #2 (dup/metric tables): **addressed** — prompt rule + R1/R2/R5
- User concern #3 (dimension completeness): **addressed** — R4 advisory at gate
