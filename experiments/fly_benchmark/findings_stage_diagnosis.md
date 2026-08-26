# Stage Diagnosis — Findings for Scenarios 10–25

> A plain-English analysis of where flights fail, by stage. This document
> only describes what the data shows — it is not a fix plan.
>
> Sources: `experiments/fly_benchmark/findings_v2.md`, `findings_v3.md`,
> `findings_v4.md`, and the per-scenario flight reports.
> Stage names match `docs/HOW_IT_WORKS.md`.

---

## 1. The seven stages, in one line each

| Stage | Name | What happens |
|---|---|---|
| 1 | Pre-check | Read the story, separate computable facts from opinions |
| 2 | Criteria | Turn facts into "must be true" checks; get them signed off |
| 3 | Dials | Draft the generator's settings (accounts, products, pricing…) |
| 4 | Calibration | Prove the dials can hit the criteria before the loop starts |
| 5 | The loop | Generate data, measure, tune the dials, repeat |
| 6 | Structure gate | Check the workbook matches the schema exactly |
| 7 | Deliver | Ship dataset + proof |

---

## 2. The tally: where flights died (scenarios 10–25)

16 flights: **4 landed** (11, 13, 14, 23), **12 did not land**.

| Stage | Flights that died here | Count |
|---|---|---|
| 2 — Criteria | 18 | 1 |
| 4 — Calibration | 15 | 1 |
| 5 — The loop | 10, 12, 16, 17, 19, 20, 22, 24, 25 | **9** |
| 6 — Structure gate | 21 | 1 |

**Most deaths happen in Stage 5 — 9 of 12 (75%).**

---

## 3. The important finding: where a flight dies is not where the mistake was made

When we trace each Stage-5 death back to its cause, most of the causes
were *made earlier* — in Stage 2 or Stage 4 — and Stage 5 was simply the
first place the system discovered them.

| Scenario | Died at | What was really wrong (and where) |
|---|---|---|
| 10 | Stage 5 | Two criteria contradicted each other (94% vs 100% on the same thing) and one used made-up territory names. **Accepted at Stage 2.** |
| 16 | Stage 5 | Two checks were signed off that don't exist at all, and the engine crashed on a missing setting. **Accepted at Stage 2/3.** |
| 19 | Stage 5 | The criterion needed a hiring/headcount *flow* the generator cannot produce. **Missing capability, Stage 3/4.** |
| 22 | Stage 5 | A criterion asked for territory potential that the data model doesn't have; it silently produced "no answer" forever. **Not caught at Stage 2/4.** |
| 24 | Stage 5 | The claim had no real measure (revenue "unpredictability"), so a different measure was substituted silently; and that substitute hit a physical ceiling. **Accepted at Stage 2, ceiling not checked.** |
| 25 | Stage 5 | A criterion demanded +101% growth the system can never produce (revenue is pinned to plan), and two criteria passed trivially no matter what. **Accepted at Stage 2, ceilings/vacuity not checked.** |
| 12 | Stage 5 | A target was arithmetically impossible without two dials moving together, and the tuning kept forgetting its own best results. **Ceiling not checked (Stage 4) + search quality (Stage 5).** |
| 17 | Stage 5 | The main metric was flat no matter what dial was turned (raking pins total revenue). **Ceiling/design, not a tuning problem.** |
| 20 | Stage 5 | Same pattern: a metric that cannot move, plus a margin predictor that drifts, plus search forgetting progress. **Mixed, mostly Stage 5.** |

Only a few deaths are genuinely Stage-5 problems — the tuning loop itself
(17 and parts of 12/20, plus the oscillation and "forgetting best result"
behavior).

---

## 4. What this means, simply put

1. **The tuning loop is not the real problem.** It is the *detector*. It
   keeps "proving" that earlier stages accepted something the generator
   cannot actually build.
2. **The real problem is acceptance.** Most Stage-5 deaths trace back to a
   criterion that should never have been signed off:
   - an impossible target (a ceiling no dial move can cross),
   - a measure that can't fail (passes trivially),
   - a claim measured by the wrong thing (silent substitution),
   - or a reference to something that doesn't exist (wrong dimension,
     made-up territory, made-up check name).
3. **The evidence is thrown away.** Stage 5 learns exactly *why* a target is
   impossible, but that knowledge is only written into a findings file. It
   never goes back to Stage 2, where it would have prevented the flight from
   starting wrong. The loop is open.
4. **The system gets more honest, not more successful.** Every death is
   cleanly diagnosed and cheap, but the landing rate has not moved much
   (20% for the 11–20 cohort and 21–25 both hover around 1–3 of 5). The
   honesty is real; the success rate is gated by the acceptance problem.

---

## 5. Side observations (worth separate thought)

- **Stage 6 caught a real bug** (scenario 21): a pre-existing column-order
  mismatch between the generator and its own schema contract. The criteria
  all passed; the structure gate caught the drift. That gate works as
  designed.
- **Stage 2 already kills some impossible contracts** — scenario 18 died at
  Stage 2 for exactly the same class of mistake scenario 10 survived to the
  loop for. So the acceptance problem is *partly* solved and partly not.
- **Landings are real.** Every landing was produced by the tuning loop with
  positive margins, including through the hardening round. When the criteria
  are buildable, the system lands quickly (often in 1 iteration).

---

## 6. Bottom line

- Stage 5 is where flights fail most, but it is the *surface*, not the root.
- The root lives in what gets accepted as a "must be true" claim, and in
  whether the data model actually has a way to produce it.
- No single stage fix changes this; the question for inspection is whether
  acceptance should be a *guarantee* (only approve what is provably
  buildable) rather than a *hope* (approve and discover).

These are the observations. A fix plan should come after this is reviewed.
