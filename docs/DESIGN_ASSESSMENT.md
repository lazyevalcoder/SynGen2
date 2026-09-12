# Design Assessment: where the failures really are, and whether this is fixable

> Status: findings + recommendation (2026-09-12). Written after the
> defect-response and capability experiments. No flight-logic change implied
> here; this is the honest read.

## 1. The question
We have spent heavily (API budget, many experiments) and the unassisted
landing rate is still low. The question this document answers: *did we
over-engineer this past the point of fixability?*

**Answer: it is over-engineered, but it is fixable — by removing layers, not
adding them.** The failures are concentrated in two known holes, and the
deterministic pieces already work.

## 2. The intern framing
Treat the LLM drafter as a competent intern. It is not a 10-year veteran.
Humanity progresses by giving workers **tools, context, and environment** —
not by adding guardrails, which stall the work.

- **Context** = what the worker knows (the engine's real capability numbers,
  examples of what worked).
- **Tools** = what the worker can do (estimate reachability, test a draft).
- **Environment** = where the worker operates (a cheap draft → test → revise
  loop, before the expensive part).

The drafter today gets a **19,000-character prompt** (story + 7.5k catalog +
5.5k rulebook) and writes JSON once. The judge's feedback is **~2% of that
prompt**. That is a manual, not a workbench.

## 3. Where flights fail (7 stages)
1. Read story → facts; 2. Criteria; 3. Dials (config); 4. Pre-flight
calibration; 5. The loop; 6. Structure gate; 7. Deliver.

Failures are **made in stages 2 and 3** (the two LLM stages) and **discovered
in stage 5** (the loop). Stage 5 is the detector, not the culprit.

## 4. What we built, and what it proved

### Defect-Response (repair path) — `docs/DEFECT_RESPONSE.md`
Triage → runbook/fixer → verify. Replayed 8 recorded failures:
- classic full re-draft: **37.5%** kept the story claims, **37.5%** fixed the
  defect, 124,567 tokens.
- defect-response: **100%** kept the claims, **75%** fixed the defect,
  **5,376 tokens** (~4%).

**Proved:** targeted, verified, minimal-context repair is far cheaper and more
claim-faithful than re-asking the full drafter.

### Capability workbench (prevention path) — `docs/CAPABILITY.md`
Numeric capability sheet (5,492 → 2,391 chars) + reachability estimator +
bounded (3-round) workbench + deterministic snap. Replayed 18 sessions:
unbuildable criteria **6 → 2**; **0 tokens** on already-buildable flights.

Full-fly A/B (`--use-capability`, scenarios 15/16/17/22):
- **22 LANDED** (4 iters) — it had failed twice before.
- 15 escalated (`criteria_geometry`), 16 escalated (iteration cap), 17
  escalated (proposal cap; AC5 −41.74).

**Proved:** when a check has a real number, the intern aims correctly and the
system can clamp — that is why 22 landed. When it doesn't, nothing changes.

## 5. The two systemic gaps

### Gap A — enforcement (blocked checks are advice-only)
`quota_vs_potential` is a **blocked path**. The capability sheet says so, the
judge names the replacement (`revenue_vs_plan`), the workbench repeats it 3×.
The drafter used it anyway (scenario 15). There is no `nearest` value to snap
for a blocked check, so the system can only re-ask and escalate. **Advice, not
enforcement.**

### Gap B — coverage (the envelope knows ~7 checks)
The capability tool only has closed forms for: `core_vs_headline_growth`,
`pipeline_concentration`, `tier_share_shift`, `avg_price_by_tier`,
`quota_vs_potential`, `revenue_vs_plan`, `effective_capacity`. Everything else
returns `reachable=None` — **no number**.
- Scenario 16 fails on `elasticity_differential`, `post_change_revenue_decline`,
  `win_rate_flat`, `activity_potential_misalignment` — none covered → the
  workbench stayed silent.
- Scenario 17's actual failures (`revenue_concentration`,
  `end_of_quarter_effect`, `deal_size_trend`) are uncovered, so the snap only
  touched AC2 and the assessor reported "buildable" **because it could not see
  them**. Silence was read as buildable.

## 6. The over-engineering
We now have **six mechanisms for one problem** ("criteria the engine can't
build"): the rulebook (skills), the capability sheet, the geometry lint, the
preflight feasibility checks, the rework judge, and the capability workbench +
snap. Each is defensible alone; together they are layers of advice on a
free-form output, and every added layer has cost a regression.

Symptoms:
- drafter prompt ~19k chars, signal ~2%;
- ~10 LLM roles, 10–70 calls per flight;
- the same failure addressed by five different places.

## 7. Recommendation: simplify, don't patch

Two options (see the closing question in the session that produced this doc):

- **B — constrain first (recommended):** keep the pipeline, but make the
  drafter choose from a **menu of buildable claim forms** and fill in numbers.
  A blocked check is not on the menu, so it cannot be chosen. This removes
  most of the failure class *without advice*, is the smallest high-leverage
  change, and tells us quickly whether the approach is sound.
- **A — full simplification:** rebuild stages 2–3 around one authoritative
  deterministic buildability gate + the menu; drop the redundant layers and
  most LLM roles. Higher effort, higher risk, but the version that could be
  reliably correct.

Either way the direction is **subtraction**: one gate, a constrained drafter
vocabulary, fewer roles, smaller prompts.

## 8. Evidence appendix
| Measurement | Value |
|---|---|
| Drafter prompt (`decompose`) | 19,005 chars; judge feedback 405 = **2.1%** |
| Config drafter (`simulator_draft`) | 18,184 chars; guidance 240 = **1.3%** |
| Skills A/B (P9.1) | Gate-1 6/6 vs 5/6; **reachability identical** |
| Classic rework replay | 37.5% claims kept; 37.5% fixed; 124,567 tok |
| Defect-response replay | 100% claims kept; 75% fixed; 5,376 tok |
| Capability replay | unbuildable 6→2; 0 tok on clean flights |
| Capability full-fly | **22 landed**; 15/16/17 escalated (coverage/enforcement) |

## 9. Honest limits
- The capability and defect-response results are replay-based; only 22 has a
  live landing to its name.
- The menu idea (option B) is untested; it is a hypothesis with strong support,
  not a proven cure.
- The envelope math can be wrong where it exists (17's snap was optimistic),
  so any expansion of coverage must ship with tests.

## 10. Update (2026-09-12): option B is implemented, not yet A/B'd
The mechanics of option B are built on `refactor/stage23-phases`, flag-gated
and default OFF: `syngen/menu.py` enforces a buildable menu (a `blocked` check
cannot be chosen), and stages 2-3 are split into small pieces consolidated in
code. See `DIVIDE_AND_CONQUER.md`. 468 tests green; no scenario runs yet.
