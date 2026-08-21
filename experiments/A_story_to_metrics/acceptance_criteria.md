# Acceptance Criteria — Discount Erosion Story

> Story: **Win rates held steady this year, but average deal discounts crept up from 12% to 18%, quietly eroding margins. The bleed is worst in EMEA, where reps are discounting aggressively to close end-of-quarter deals.**

These are the targets the generated dataset must satisfy. The validator (Experiment C) checks each one against the Excel workbook. Status: **RECONCILED** — human draft cross-checked against independent LLM decomposition (`llm_decomposition.md`); divergences resolved below.

## Dataset assumptions
- Time horizon: FY26 Q1–Q4
- Regions: AMER, EMEA, APAC
- ~60 accounts, ~400 opportunities (~100/quarter)
- Opportunity lifecycle: created → open stages → Closed Won / Closed Lost

## Criteria

| # | Criterion | Target | Tolerance | Source claim |
|---|-----------|--------|-----------|--------------|
| AC1 | Overall win rate is flat across quarters | each quarter within ±3pp of annual mean | hard | "win rates held steady" |
| AC2 | Avg discount % in Q1 | 12% | ±2pp | "crept up from 12%" |
| AC3 | Avg discount % in Q4 | 18% | ±2pp | "...to 18%" |
| AC4 | Discount trend rises Q1→Q4 | no quarter's avg dips >1pp below prior quarter's avg | soft | "crept up" |
| AC5 | EMEA avg discount premium over AMER and APAC (H2 = Q3+Q4 combined) | ≥ +5pp vs each region | hard | "bleed is worst in EMEA" |
| AC6 | End-of-quarter effect: deals closed in final 14 days of a quarter have deeper discounts than deals closed mid-quarter (days 15–74) | ≥ +5pp difference, averaged across quarters | hard | "discounting aggressively to close end-of-quarter deals" |
| AC7 | Realized revenue as % of list price declines across the year | Q1 ≈ 88%, Q4 ≈ 82% | ±2pp | "quietly eroding margins" |
| AC8 | Data sanity: discount ∈ [0%, 40%], amounts > 0, all account FKs valid, close dates within their quarter | 100% compliant | hard constraint | realism |

## Notes on definitions
- **Win rate** = Closed Won / (Closed Won + Closed Lost), per quarter.
- **Avg discount** = mean of (list_price − realized_price) / list_price over **Closed Won** deals only (lost deals never realize a discount).
- **Realized revenue % of list** = sum(realized_price) / sum(list_price) over Closed Won, per quarter.
- **End-of-quarter** = close date within final 14 calendar days of the quarter.

## Open questions resolved
- Discounts measured on won deals only (lost deals carry a proposed discount but it never materialized — excluded from trend claims). *LLM agreed (its ambiguity D).*
- AC5 scoped to H2 so the "worst in EMEA" claim has room to emerge rather than being true from day one.

## Cross-check vs LLM decomposition (Ornith-1.5-35B)

The LLM produced 5 criteria (C1–C5) mapping to our AC1–AC7 almost 1:1. Verdict: **convergent**. Divergences and resolutions:

| Topic | Human draft | LLM | Resolution |
|-------|-------------|-----|------------|
| Win rate steadiness | ±3pp of annual mean | ±3pp of annual mean | Identical → keep |
| Discount trend | no dip >1pp below prior quarter | same | Identical → keep |
| Q1/Q4 discount tolerance | ±2pp | ±1.5pp | Keep **±2pp** (kinder to generation; still tight enough to be meaningful) |
| EMEA premium | ≥ +5pp, H2 only | ≥ +2pp, full year | Keep **≥ +5pp in H2** (clearer signal, room to emerge) |
| End-of-quarter window | final 14 days, ≥ +5pp | final 30 days, ≥ +3pp | Keep **final 14 days, ≥ +5pp** (sharper "quarter-end crunch"; validator tests both windows anyway) |
| Margin erosion (AC7) | realized/list price ratio 88%→82% | flagged as NOT computable without cost data | Our AC7 already avoids this trap — realized/list is computable without cost data and is a valid margin proxy. LLM's objection applies to true gross margin, which we deliberately don't claim. |
| Rep attribution | not included | suggested `owner_id` field | Adopt: add `owner` column to opportunities in Experiment B for realism (not a validated criterion) |
| Data sanity (AC8) | hard constraints | equivalent data-quality checks | Aligned |

## Experiment A verdict
**PASS (pending owner sign-off).** A story can be decomposed into script-checkable criteria, and an independent LLM decomposition converges with the human draft on substance while differing only on tolerance magnitudes and window definitions — exactly the ambiguities we predicted. The reconciliation table above becomes part of the harness's future "spec clarification" step.
