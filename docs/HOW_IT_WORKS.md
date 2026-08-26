# How SynGen Works

A plain-English tour of how a business story becomes a realistic synthetic
dataset — and the safety nets that make sure the result is honest.

---

## 1. What this is

You give SynGen a *story* about a business (for example: *"our average deal
size fell by half this year while win rates stayed flat"*). SynGen turns that
story into a **realistic fake dataset** — accounts, opportunities, pricing,
timing — that actually matches what the story says, and it ships a **proof**
that the match is real, not claimed.

It is called a "flight": the story takes off, travels through several stages,
and either **lands** (dataset delivered with proof) or **escalates** (it
tells you exactly why it could not be done, instead of quietly faking it).

## 2. The big idea

A story is language. Data is numbers. SynGen bridges the gap with two
"contracts":

1. **Criteria (what must be true)** — small, measurable statements such as
   *"average deal size in Q4 is 40–60% lower than Q1"*. These are the
   landing targets.
2. **Dials (how to build it)** — the generator's settings: how many
   accounts, what products, what pricing, what timing. These are the
   controls.

The generator builds a workbook from the dials. Then an **autopilot** tunes
the dials until every criterion passes. If the dials can't reach a
criterion, the system says so — it never pretends.

Every stage below has a *safety net*: a deterministic check that catches
mistakes before they waste a flight, or an honest escalation when something
is genuinely impossible.

---

## 3. The journey, stage by stage

### Stage 1 — Read the story and sort facts from opinions
*(code: `intake.precheck_claims`)*

The system reads the story and splits it into individual claims. Each claim
is marked:

- **(+) Computable** — the data could prove or disprove it.
  *Example: "average deal size fell from ~$60k to ~$30k".*
- **(-) Not computable** — an opinion, motivation, or outside-the-data event.
  *Example: "reps chased smaller, faster wins" (intent) or "a new comp plan
  kicked in" (an HR event the tables don't carry).*

It also asks the reader a few **clarifying questions** where a claim depends
on something the story doesn't say (e.g. "is there a field that separates
deal size from deal count?").

*Safety net:* only computable claims are allowed to become landing targets.
Opinions are set aside up front — no criterion can be built on them.

### Stage 2 — Turn facts into criteria, and get them approved
*(code: `intake.draft_criteria`, `intake.enforce_coverage`, `critic`,
`criteria_lint.lint_criteria_internal`)*

1. **Draft** — a model writes a first set of acceptance criteria (AC1, AC2,
   …) from the computable claims. Each criterion names one measurable check
   and its target numbers.
2. **Coverage guard** — every computable claim must be *covered* by at least
   one criterion. If a claim is left uncovered, the criteria are re-drafted
   once. If the gap is really a missing measurement primitive (a "vocabulary
   gap"), it is recorded as a note rather than ignored. If nothing is
   covered even after re-drafting, the flight escalates honestly.
3. **Critic pass A** — a second model reads the story and the criteria
   together and looks for *intent* mistakes that pure math can't see:
   dropped claims, or a criterion that points the wrong way (says "increase"
   where the story says "decrease"). Block-level findings trigger one
   corrective re-draft.
4. **Consistency lint** — a deterministic check proves the criteria aren't
   jointly impossible (e.g. two criteria that fight each other). A conflict
   gets one re-draft; a persistent conflict escalates.
5. **Gate 1** — the reader signs off on the criteria. They can also type
   overrides (`AC3.max_discount_pct=90`) instead of starting over.

*Safety net:* no vacuous criteria, no contradictory criteria, no
uncovered claims, and a second opinion on intent — all before the expensive
part begins.

### Stage 3 — Draft the generator's dials
*(code: `spec.draft_simulator`, `critic` pass B, `linter.lint`)*

1. The system drafts **simulator.json** — the dials. It includes:
   - **accounts** — how many, which segments and territories
   - **products** — the catalog, tiers, price multipliers, share weights
   - **opportunities** — deal size distribution, discounts, stages, timing
   - **time model** — quarters and their end dates
   - **planning** — quota, targets, attainment
   - **forecast / outlier deals / ownership** — the optional blocks a story
     may need
2. **Critic pass B** — a second model checks the dials against the criteria:
   can these settings plausibly produce what the criteria demand? Block
   findings trigger one corrective re-draft of the dials.
3. **Schema lint** — a deterministic check that the dials file is shaped
   correctly and internally consistent (regions, segments, products all
   match each other).
4. **Calendar sync** — the quarter dates from the dials are written back
   into the criteria so the proof uses the same calendar the generator used.

*Safety net:* a structurally broken or self-contradictory dial file is
caught here, before generation.

### Stage 4 — Pre-flight calibration: prove the dials can hit the targets
*(code: `preflight.calibrate` / `autocalibrate` / `repair_criteria`,
`criteria_lint.cross_lint`)*

This is the "measure twice, cut once" stage.

1. **Calibration** — deterministic math solves for the dial values the
   criteria imply: revenue-share targets become product mix settings, a
   coverage multiple becomes a pipeline size, a margin target becomes a
   discount curve, and so on. If the draft is already correct, nothing
   changes (that's a good sign).
2. **Repair** — criteria that reference things the calendar can't contain
   (like a quarter before the data starts) are fixed deterministically
   rather than left to fail later.
3. **Geometry lint** — every criterion must point at something that actually
   exists in the dials (a real segment, a real product tier, a real
   dimension). If a criterion references a made-up unit, the criteria get
   one corrective re-draft with a hint for the expressible form; if it still
   can't be expressed, the flight escalates *before* burning iterations.

*Safety net:* the most expensive mistake in the system — spending a whole
flight proving a target is unreachable — is caught here, up front, whenever
the math can see it.

### Stage 5 — Generate, measure, tune: the autopilot loop
*(code: `generator.engine.generate_to_workbook`, `converge.run_convergence`)*

1. **Generate** — the engine builds the actual workbook (accounts,
   opportunities, quota, forecast) from the dials.
2. **Measure** — every criterion is checked against the real workbook. Each
   gets a verdict (PASS/FAIL) and a **margin** (how far past the target, or
   how far short).
3. **If all pass → landed.** The system then does a **hardening round**: any
   criterion with a thin margin gets one more tune to make the landing
   comfortable, not lucky.
4. **If some miss** — the autopilot proposes dial changes (a model explains
   each change in plain English: *"raise the premium price multiplier to
   lift premium's revenue share"*), regenerates, and re-measures.
   - Proposals that make things *worse* are reverted to the best state seen
     so far.
   - A few deterministic **remedies** fix specific known patterns
     (e.g. rebalance quota against market potential, or add a rising
     headcount flow when the story needs growth).
   - If the loop stalls, it bumps the random seed once — a fresh roll of the
     dice — before giving up.
5. **Stale-set detector** — if the same criteria pass unchanged for several
   rounds while others *never* cross, the autopilot stops and **escalates
   with the reason**: *"the remaining failures are not reachable by knob
   turns."* It names the worst margins. This is the honesty guarantee — the
   loop never grinds forever pretending.

*Safety net:* the loop can't run forever, can't regress silently, and can't
die in silence. Escalation means *explained*, not *abandoned*.

### Stage 6 — Structure gate + final proof
*(code: `linter.structure_findings`, `pipeline.run_validation_final`)*

1. **Structure gate** — the workbook's sheets and columns must match the
   engine's contract exactly. No missing sheets, no surprise sheets, no
   columns that drifted out of order. This catches hand-edited output or a
   generator that silently changed shape.
2. **Final validation** — all criteria are re-measured against the final
   workbook and written into `validation_report.md`, the proof that ships
   with the dataset.

*Safety net:* the delivered file is guaranteed to match the schema contract,
and the proof is generated, not asserted.

### Stage 7 — Deliver

Three files, saved to the session folder:

- **`dataset.xlsx`** — the synthetic data itself
- **`validation_report.md`** — the proof (criteria table with verdicts)
- **`simulator.json`** — the dials, so anyone can tweak a knob and
  regenerate without re-asking the model

---

## 4. Safety nets at a glance

| Guard | Stops |
|---|---|
| Claim pre-check | opinions becoming landing targets |
| Coverage guard | criteria that don't cover the story's facts |
| Consistency lint | criteria that contradict each other |
| Critic (A & B) | intent errors: dropped claims, inverted directions |
| Geometry lint | criteria referencing data that doesn't exist |
| Pre-flight calibration | spending a flight on unreachable targets |
| Stale-set detector | endless pointless tuning |
| Structure gate | schema drift / hand-edited workbooks |
| Fail-open critic | a broken critic killing a flight |

---

## 5. A real journey: Scenario 23

Here is an actual flight, end to end, exactly as the system processed it.

**The story (the input):**

> After the new compensation plan kicked in, our average deal size fell from
> about 60 thousand dollars in Q1 to roughly 30 thousand by Q4 as reps
> chased smaller, faster wins. Win rates stayed essentially flat all year —
> the mix just got smaller.

**Stage 1 — sorting facts from opinions.** The pre-check found 5 claims and
asked 4 questions. Two claims made the cut:

- **(+)** average deal size fell from ~$60k to ~$30k
- **(+)** win rates stayed essentially flat all year

Three were rejected as non-computable:

- **(-)** a new compensation plan kicked in *(an HR event, not in the
  tables)*
- **(-)** reps chased smaller, faster wins *(motivation / intent)*
- **(-)** the mix just got smaller *(causal explanation, not a fact)*

The 4 questions asked things like: *"is there a date field enabling quarter
grouping?"* and *"is there a field distinguishing deal size from deal
count?"*

**Stage 2 — criteria + the double-check.** A draft set of criteria was
written; the critic flagged 2 block issues, so the criteria were re-drafted.
The final three, signed off at Gate 1:

| ID | Check | Target |
|---|---|---|
| AC1 | deal size trend | ~-50% by Q4, ±8pp tolerance |
| AC2 | win rate flat | within 3pp of the year's mean |
| AC3 | data sanity | no discount above 80% |

No coverage gaps — all computable claims were covered, so the coverage
guard stayed quiet.

**Stage 3 — dials + critic B.** The generator dials were drafted. Critic B
flagged 2 issues in the config; one corrective re-draft fixed them. The
schema lint passed (one advisory note about the segment taxonomy, which is
informational only).

**Stage 4 — calibration.** The dials were already consistent with the
criteria, so calibration changed nothing. Nothing to repair, no geometry
findings. Straight through.

**Stage 5 — the loop.** Generate, measure, and the verdict came back on the
first try:

```
ID    Verdict  Actual                   Target                         Margin    Criterion
--------------------------------------------------------------------------------------------
AC1   PASS     -43.5% deal size         -50% +/-8pp                    +1.47     deal_size_decline_direction
AC2   PASS     2.80pp dev (FY26-Q2)     <= 3pp of mean                 +0.20     win_rate_flat_anchored
AC3   PASS     clean                    no violations                  +1.00     data_referential_sanity
--------------------------------------------------------------------------------------------
3/3 criteria passed - STORY LANDED
```

3/3 passed — but AC2's margin (+0.20pp) was thin, so the system ran a
**hardening round** instead of stopping. It tuned once more:

```
ID    Verdict  Actual                   Target                         Margin    Criterion
--------------------------------------------------------------------------------------------
AC1   PASS     -56.7% deal size         -50% +/-8pp                    +1.26     deal_size_decline_direction
AC2   PASS     2.40pp dev (FY26-Q1)     <= 3pp of mean                 +0.60     win_rate_flat_anchored
AC3   PASS     clean                    no violations                  +1.00     data_referential_sanity
--------------------------------------------------------------------------------------------
3/3 criteria passed - STORY LANDED
```

Deal size now sits at -56.7% (comfortably inside -50% ±8pp), win-rate spread
tightened to 2.40pp, all margins positive.

**Stage 6 — structure gate + proof.** The workbook matched the schema
contract, and `validation_report.md` was generated with the table above.

**Stage 7 — delivery.** The session shipped `dataset.xlsx`,
`validation_report.md`, and `simulator.json` — a dataset that genuinely
shows deal size halving while win rate holds flat, with proof.

---

## 6. An honest note: not every flight lands

Scenario 23 is a clean landing, but the system does not always land — and it
was designed to say so out loud rather than fake it. Across the 25-flight
certification cohort, 6 landed and the rest escalated with a recorded,
specific reason. Examples of honest escalations:

- **Scenario 22** — a criterion needed a market-potential figure that the
  generated plan didn't contain; the flight escalated naming the missing
  dimension.
- **Scenario 24** — a criterion demanded the top-3 customers hold 60% of
  revenue, which the generator's own heavy-tail mechanics physically
  cap below; the autopilot proved it unreachable and escalated.
- **Scenario 25** — two criteria were accepted that passed trivially no
  matter what (a $1 billion cap, a zero-tolerance gap); that is a bug in
  the *criteria approval* stage, and it's recorded as one.

Every escalation is logged with its diagnosis in `findings_v4.md`, so the
system gets measurably more honest — and more buildable — over time. The
goal is not a 100% landing rate; it's a system that never lies about
whether it landed.

*Continue reading: `docs/DOMAIN_PACKS.md` for the engineering history,
`docs/JOURNEY_PLAN.md` for the observability design, and
`experiments/fly_benchmark/findings_v4.md` for the flight record.*
