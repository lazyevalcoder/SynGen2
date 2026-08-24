# SynGen — Project Overview

*For senior-management review. Work in progress, progressing well.*

## What

SynGen is an AI-native harness that converts a plain-language business story into a realistic, multi-table synthetic dataset **and proves that the dataset tells that story**.

A user writes a narrative — for example (revenue operations): *"SMB revenue beat plan by 4%, but ARR per customer fell 8% because most new bookings came through the entry price band while discounting crept upward."* SynGen responds by:

1. Translating the narrative into measurable acceptance criteria (each claim becomes a checkable statement with a numeric target and tolerance),
2. Designing and generating a synthetic dataset that satisfies them,
3. Validating the finished workbook against every criterion,
4. Delivering the data together with a proof report — or escalating with a precise explanation of what the current data model cannot express.

The output is not "plausible random data." It is data engineered to demonstrate a specific business narrative, with reproducible generation (same seed → same file) and an audit trail from every number back to its generating configuration.

## Why

**The problem.** Analytics, enablement, and tooling work stalls on data availability. Real data is slow to obtain, privacy-gated, and shape-frozen: the moment someone wants a new table, field, or business scenario, everything queues behind governance. Traditional synthetic generators solve availability but not trust — they produce plausible-looking rows that demonstrably encode no particular business story, so nothing built on them can be meaningfully demonstrated.

**The bet.** Large language models are excellent at translating human intent into structured specifications, but unreliable at arithmetic, calibration, and self-verification. Deterministic software is the opposite. SynGen's architecture puts each where it is strong: the LLM translates; deterministic machinery calculates, generates, and proves.

**Why this matters strategically.** The harness itself is domain-agnostic. The first domain pack (revenue operations) proves the method; additional verticals are additive packages, not rebuilds. Data generation becomes something a team does *on demand* — a capability rather than a project.

## How

### The pipeline at a glance

```
Story (plain language)
   │
   ▼
[1] Criteria design ── LLM decomposes story → measurable criteria ──► HUMAN GATE 1
   │
   ▼
[2] Draft + auto-calibration ── LLM drafts config;
    deterministic solvers correct it exactly
   │
   ▼
[3] Fixed generator ── declarative config in, tables out (no generated code)
   │
   ▼
[4] Black-box validation loop ── re-derives every criterion from the workbook;
    adjusts declared knobs until all pass ──► HUMAN GATE 2
   │
   ▼
Deliverables: dataset.xlsx + validation_report.md + simulator.json
(reproducible, auditable, regenerable)
```

### Core components

| Component | Role | Nature |
|---|---|---|
| **Decomposer** | Story → measurable acceptance criteria | LLM + fixed check vocabulary |
| **Schema linter** | Catches structurally impossible designs before any compute | Deterministic rules |
| **Drafter** | Criteria → declarative generator config | LLM |
| **Pre-flight calibrator** | Solves levels, mixtures, plans and prices *exactly*; flags what it cannot solve | Pure math — no AI |
| **Generator engine** | Config → multi-table dataset with derived-field integrity guarantees | Fixed code, versioned |
| **Validator** | Black-box re-derivation of every criterion from the delivered file only | Deterministic checks |
| **Convergence loop** | Adjusts declared knobs until criteria pass; escalates honestly when they can't | LLM proposals + numeric margins |
| **Session store** | Append-only history of every iteration, config, and report | Files — replayable |

### Why this architecture doesn't accumulate heavy technical debt

Three deliberate constraints do most of the work:

**1. The generator never executes generated code.** Every scenario is expressed as *data* (a JSON config), interpreted by one fixed engine. New behaviors ship as engine features that are versioned, unit-tested both ways (present-and-passing, absent-and-still-correct), and locked by a golden-anchor test that proves old scenarios reproduce byte-identically after changes. There is no growing pile of per-scenario scripts to rot.

**2. Validation is black-box.** Checks read only the delivered workbook — never internal state. This means the proof layer cannot drift from reality: if the generator changes underneath, the validator still measures what the customer actually receives. It also means new domains reuse the same proving mechanism unchanged.

**3. Every failure becomes permanent infrastructure.** When a live run exposes a flaw, the fix lands as a general rule — a linter rule, a solver, a check, or a prompt constraint — never as a special case keyed to that scenario. The project keeps an explicit defect ledger; each entry closes with the structural fix that makes the whole class of failures impossible, not just the observed instance.

The practical consequence: complexity grows as *additive, isolated building blocks* (a check ≈ thirty lines plus a registry entry plus tests), while core contracts stay stable.

### Why a feature change doesn't become a rabbit hole

The system is designed so that failures are loud, local, and instructive:

- **Two human gates** mean nobody sees generated data until the acceptance criteria are approved, and delivery happens only against those approved criteria.
- **Structural honesty**: when a story demands something outside the current data model, the system escalates immediately with a precise statement of the gap — it never thrashes silently or delivers subtly wrong numbers.
- **Deterministic pre-flight**: the arithmetic a naive system would hope the LLM "gets right" is instead solved exactly before generation starts (target levels, product mixes, plan ratios). What the solvers cannot fix is surfaced to a bounded correction loop, and then to a human — with reasons.
- **Replayability**: every session stores its full iteration history. Any past result can be reproduced, diffed, or extended without archaeology.

Adding a new analytical concept follows the same three-step pattern every time: register a check (~30 lines), describe it to the decomposer/drafter vocabularies, add tests in both directions. Recent examples built this way include quota attainment, product-margin coupling, territory rollups, and open-pipeline lifecycle behavior.

### Growth path: domain packs

The harness (loop, gates, solvers, sessions) is domain-neutral. A new vertical is a *pack*: entity definitions, a metric-check library, and prompt vocabulary following the canonical-model interface already documented. The first pack proves the seam; subsequent packs are fractions of the effort.

### On learning

Today the system learns within a session (measured cause-and-effect feedback steers each adjustment) and between sessions through curated lessons folded into its playbooks and guardrails. A natural future step is case memory — retrieving past landed configurations and calibration solutions as examples for new stories. Deliberately, no stronger claims about recursive self-learning are made until the system demonstrates what is worth learning.

### A worked example, end to end

Take the revenue-operations story from earlier: *"SMB beat plan by 4%, but ARR per customer fell 8% on entry-price mix while discounting crept up."*

1. **Decompose.** The LLM returns criteria such as *"SMB quota attainment is 104% ±2pp"* (checked against a generated plan sheet), *"entry-tier share of won revenue grows from ~25% to ~45%"* and *"average discount rises from 12% to 18%."* Ambiguities are flagged with the assumption chosen; a human approves or edits.
2. **Draft + calibrate.** The LLM drafts a config: account segments and regions, a product catalog with entry/core/premium tiers and their margins, per-region discount curves, and a quarterly quota plan. The deterministic calibrator then solves the arithmetic exactly — it computes what each region's base discount must be for the blended level to land on target, adjusts product count-shares so the entry tier's *revenue* share (not just deal-count share) hits its mark, and sets attainment ratios so actuals meet plan precisely.
3. **Generate & prove.** The engine produces accounts, opportunities (with products, discounts, lifecycle stages), a plan sheet, and a derived summary. The validator re-derives every criterion from the workbook alone and prints a table: each claim, actual vs. target, and its numeric margin of safety.
4. **Deliver or escalate.** If a criterion can't be met by knob adjustment — because it references something outside the data model — the loop stops immediately and states exactly what is missing. Wrong data delivered quietly is the one failure mode the architecture refuses.

The whole run leaves an append-only session folder: every iteration's config and validation report. Re-running with the same seed reproduces the same file byte-for-byte.

### Questions we expect

**"What happens when someone brings a genuinely new scenario?"**
Two things, both by design. First, the system tries to express it from its existing vocabulary of general building blocks — most narrative claims decompose into combinations of levels, trends, mixtures, plans, and correlations that already exist. Second, if it truly cannot, it escalates *honestly*: it names the missing capability instead of producing data that silently fails the story. Escalations feed the roadmap; each one historically converts into a reusable building block, not a patch.

**"Is this just memorizing demo scenarios?"**
No scenario-specific logic exists anywhere in the codebase. Scenarios live entirely as data: story text, acceptance criteria, and configuration values. That is enforced structurally — the engine only understands declarative primitives (distributions, curves, weights, plans), so there is nowhere to hide special cases.

**"Does it learn?"**
Within a run, yes: every adjustment records its measured effect, and that feedback steers the next step. Across runs, lessons are curated into playbooks and guardrails between engagements. A retrieval-based case memory (reusing past solved configurations as examples) is a natural future extension; stronger claims about recursive self-learning are deliberately not made until the system demonstrates what is worth learning.

---

*SynGen — story-in, provable data-out.*
