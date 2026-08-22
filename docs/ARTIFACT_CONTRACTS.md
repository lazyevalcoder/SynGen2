# SynGen Artifact Contracts

> **Status:** v1 draft. These file schemas ARE the APIs between phases. Every phase reads/writes only these artifacts — no hidden state. Changes to any schema here require updating this doc first.
>
> Design rule from Experiment B: if a phase can't be tested by hand-crafting its input files in isolation, the contract is wrong.

---

## Artifact Flow

```
story.md ──> criteria.json ──> spec.md ──> simulator.json ──> dataset.xlsx
                                   │                            │
                                   └──> assumptions.log          └──> validation_report.json
                                                                      │
                                                                      └──> knob_deltas.json (loop-internal)
```

---

## 1. `story.md` — Input Story

Free-form markdown from the user. No schema constraints beyond:

```markdown
# Story: <short title>

<2–6 sentence business narrative. Claims must be falsifiable against
tabular data. The harness will reject stories containing unverifiable
claims ("morale was low") with an explanation.>
```

**Validation rules on intake:**
- Must contain at least one quantitative claim or comparison ("steady", "crept up", "worst in")
- Harness runs a pre-check LLM pass: lists every claim + flags non-computable ones *before* Phase 1 proper (Experiment A's margin/cost-data lesson)

---

## 2. `criteria.json` — Acceptance Criteria (Phase 1 output)

Machine-readable objective function. Validated shape (proven in Experiment C):

```jsonc
{
  "meta": {
    "story_ref": "story.md",
    "created": "2026-08-21",
    "llm_model": "ornith-1.5-35b",           // model that drafted it
    "human_signoff": true                     // Gate 1 must be true to proceed
  },
  "definitions": {                             // shared metric semantics — pinned explicitly
    "discount_scope": "closed_won_only",       // per A's reconciliation
    "win_rate": "closed_won / (closed_won + closed_lost), per quarter",
    "weighting": "simple_average | revenue_weighted"   // D's lesson: pin weighting!
  },
  "criteria": [
    {
      "id": "AC1",                             // stable ID, never reused
      "name": "Win rate flat across quarters", // name must match definition exactly (C's lesson)
      "check": "win_rate_flat",                // registered check-function name
      "params": { "band_pp": 3.0 },
      "classification": "statistical",         // statistical | parametric — drives loop strategy
      "source_claim": "win rates held steady"  // traceability back to story text
    }
  ]
}
```

**Contract rules:**
- Every criterion MUST have a `check` implementation registered in the validator; intake rejects unknown check names
- `classification` is set in Phase 1 review, consumed by Phase 4 loop
- Tolerances live inside `params` per check type

---

## 3. `spec.md` — Data Spec (Phase 2 output)

Human-readable spec produced after persona critique. Structure (consumed by Phase 3 authoring):

```markdown
# Data Spec: <title>

## Resolved ambiguities        <!-- each with chosen resolution + who resolved -->
- "end-of-quarter" = final 14 days of quarter [human]

## Entities & dimensions       <!-- what tables exist, their grain -->
## Relationships               <!-- FKs, cardinality -->
## Time model                  <!-- horizon, quarter definitions, date rules -->
## Assumptions                 <!-- hardcoded values, e.g., region count -->
## Out of scope                <!-- claims personas agreed NOT to model -->
## Persona dissent             <!-- unresolved disagreements, for the record -->
```

**Contract rules:** every entry in `assumptions` must map to a simulator.json knob or generator constant — no orphan assumptions.

---

## 4. `simulator.json` — Knob Engine (Phase 3 input)

The proven shape (Experiment B/D), formalized:

```jsonc
{
  "seed": 42,                                  // determinism guarantee
  "time_model": {
    "fiscal_year": "FY26",
    "quarter_labels": ["FY26-Q1", "..."],
    "quarter_end_dates": ["2026-03-31", "..."]
  },
  "output": { "workbook": "output/dataset.xlsx" },
  "entities": {                                // generalized from B's accounts block
    "<entity_name>": {
      "count": 60,
      "fields": { "<field>": { "type": "categorical|lognormal|normal|uniform",
                               "values_or_params": {} } }
    }
  },
  "facts": {                                   // e.g., opportunities
    "per_period": 400,
    "rates": { "win_rate": 0.27, "win_rate_jitter": 0.005 },
    "outcome_assignment": "bernoulli | exact_count",   // D's lesson: quota mode escape hatch
    "derived_fields": {                          // computed, not sampled
      "realized_price": "list_price * (1 - discount_pct/100)"
    },
    "effects": [                                 // named, composable adjustments
      { "name": "region_discount_curve",
        "target_field": "discount_pct",
        "base_by_group": { "<group>": [/* per-period values */] },
        "noise_sd_pp": 3 },
      { "name": "end_of_quarter_boost",
        "target_field": "discount_pct",
        "boost_pp": 6.5,
        "window_days": 14,
        "share_in_window": 0.30 }
    ],
    "bounds": { "discount_pct": [0, 40] }
  },
  "quota": {                                   // OPTIONAL - WS3 aggregate targets
    "by_segment": {                            // segment -> per-period revenue targets
      "Enterprise": [1200000, 1250000, 1300000, 1400000]
    }
  }
}
```

**Contract rules:**
- Generator NEVER contains business numbers — all live here (B's zero-code-change result)
- Adding a new effect type = generator code change (versioned, tested); adding a new value = config change only
- BOM-free UTF-8 enforced by tooling (D's PowerShell lesson)

**Quota block & raking (WS3, M4):**
- When `quota` is present the engine emits a `quota_plan` sheet and runs a deterministic **monetary raking pass**: per segment x period stratum, `list_price` is scaled so closed-won realized revenue hits the target; `realized_price` is then recomputed from the scaled list, preserving the derived-field identity exactly
- Raking touches ONLY monetary fields — discounts, win rates, dates, and counts are untouched, so it is orthogonal to every distribution-level check
- Attainment criteria (`revenue_vs_plan`) therefore verify configuration intent against generated data black-box; they should not fail on converged configs unless segments/quota keys mismatch

---

## 5. `dataset.xlsx` — Output Workbook

Multi-sheet Excel. Sheet contract:

| Sheet | Required | Contents |
|-------|----------|----------|
| `<entity>` sheets (e.g., `accounts`) | yes | One row per entity instance; `*_id` primary keys |
| `<fact>` sheet (e.g., `opportunities`) | yes | FK columns valid, dates typed, derived fields present |
| `quarterly_summary` (or period summary) | yes | Derived from fact rows ONLY — never authored independently |
| `quota_plan` | when `quota` block present | One row per segment x period: target revenue; the plan actuals are measured against |
| `_synngen_meta` | yes | seed, config hash, generation timestamp, criteria version |

Validator reads entity+fact sheets only for distribution checks (black-box); `revenue_vs_plan` additionally reads `quota_plan` when a criterion references it. `_synngen_meta` is for humans/repros.

---

## 6. `validation_report.json` — Loop Signal (Phase 4 internal)

Machine-consumable twin of the human PASS/FAIL table:

```jsonc
{
  "workbook": "output/dataset.xlsx",
  "config_hash": "a1b2c3",
  "iteration": 3,
  "overall": { "passed": 7, "total": 8, "exit_code": 1 },
  "results": [
    {
      "id": "AC6",
      "verdict": "FAIL",
      "actual": "+4.79pp gap",
      "actual_numeric": 4.79,
      "target_numeric": 5.0,
      "margin": -0.21,              // distance from passing; positive = safety
      "detail": "EOQ avg=19.92% (n=121), mid-quarter avg=15.13% (n=242)"
    }
  ]
}
```

**Contract rules:** `margin` is mandatory for every criterion — D's thin-margin lesson (+0.03pp) means the loop needs distance-from-threshold, not just verdicts. Human table view is rendered FROM this file, never separately maintained.

---

## 7. `knob_deltas.json` — Loop Proposal (Phase 4 internal)

What the knob-proposer emits each iteration:

```jsonc
{
  "iteration": 3,
  "diagnosis": [
    { "criterion": "AC6", "type": "parametric",
      "reason": "gap runs ~0.7pp under configured boost" }
  ],
  "changes": [
    { "path": "$.facts.effects[1].boost_pp", "from": 5.5, "to": 6.5,
      "expected_effect": "AC6 gap +1.0pp" },
    { "path": "$.facts.effects[0].base_by_group.AMER[0]", "from": 12, "to": 11.5,
      "expected_effect": "compensate AC2 stacking", "compensates_for": 0 }
  ],
  "transfer_function_notes": "won_avg = blend(base, region_mix) + share*boost"
}
```

**Contract rules:** every delta carries predicted effect + compensation linkage — this is how D's stacking lesson gets encoded into automation.

---

## 8. Session Layout — Replay & Tweak Contract

Every project lives in one self-contained folder. Users return, tweak, regenerate.

```
sessions/<date>_<story-slug>/
├── story.md                    # current story text (versioned: story.v1.md, story.v2.md...)
├── story_diff.json             # diff classification between story versions
├── criteria.json               # current acceptance criteria (with depends_on edges)
├── spec.md                     # approved data spec
├── simulator.json              # CURRENT knobs (the only file users normally edit)
├── history/                    # immutable prior configs + reports, one per iteration
│   ├── iter01_simulator.json
│   ├── iter01_validation_report.json
│   └── ...
├── output/dataset.xlsx         # latest generated workbook
├── validation_report.json      # report for the latest workbook
└── session_log.md              # full prompt/gate/iteration memory
```

**Rules:**
- `history/` is append-only; everything else reflects current state
- Regeneration with same seed + same config MUST reproduce the same workbook (data-level determinism)
- Story tweaks classify into: **parametric** (Phase 4 loop only), **taxonomy addition** (config edit), **structural** (re-enter Phase 2). Validated happy paths: first two (Experiment F); structural is a known edge case (GAPS G11)
- Amending one criterion must trigger dependency propagation before Gate 1 re-approval (GAPS G10)

### criteria.json amendment: `depends_on` edges

```jsonc
{
  "id": "AC7", "check": "realized_vs_list",
  "depends_on": ["AC3"],        // AC7's end target = f(AC3 target); diff classifier
                                 // must propose AC7 amendment whenever AC3 changes
  "params": { "...": "..." }
}
```
