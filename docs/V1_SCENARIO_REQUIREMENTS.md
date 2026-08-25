# SynGen V1 Scenario Requirements

> **Source:** `JUNK_NOT_PROJECT_RELATED/Narratives - Synthetic generation.md` (25 RevOps narratives).
>
> **Definition of Done for v1:** every scenario below can be landed end-to-end through the SynGen harness — story in, validated multi-sheet dataset out, all acceptance criteria green — following the standard discipline (each new capability isolated and proven on one story before generalizing).
>
> **Status:** capability assessment done August 2026 against M2 codebase. This doc is the de-facto requirements list for completing v1.

---

## 1. Capability Gap Summary

**Legend:** ✅ shippable today · 🟡 covered by roadmap once listed primitives/entities land · 🔴 requires structural work beyond distribution knobs (process/state modeling)

| # | Scenario theme | Verdict | Blocking capabilities |
|----|---------------|---------|----------------------|
| 3 | SMB beat plan, entry-price mix, discount creep | ✅ | **LANDED (M5 iter 4):** WS2 products + WS8 tier calculus; entry-mix beat certified 5/5 (m5i4s3) |
| 6 | Ent missed / MM beat via quota-vs-potential mismatch | ✅ | **LANDED (M4):** quota block + raking + revenue_vs_plan; market_potential_usd on accounts (WS1-lite) |
| 7 | Bookings -3%, pipeline creation +12% (low-ICP mix) | ✅ | **LANDED (M5 iter 1):** icp_share + icp_sampling_weights_by_quarter + deal_size_trend + icp_creation_shift |
| 8 | COGS↑, discounts concentrated in high-margin products | ✅ | **LANDED (M5 iter 3):** 9/9 via pre-flight auto-calibration (margin-spread solver + tier-share closed form) |
| 12 | Comp plan → entry-tier deals + discounting, margin ↓ | ✅ | **LANDED (M5 iter 2):** products block + blended_margin_trend + tier_share_shift + avg_price_by_tier; 5/5 certified |
| 15 | Quotas 20–25% above addressable market | ✅ | **LANDED (M5 iter 4):** quota_vs_potential: EMEA-Central at ~124% of addressable market vs whitespace territories ~40% (m5i4s15) |
| 18 | Gap concentrated in bottom-quartile territories | ✅ | **LANDED (M5 iter 3):** territory split fix + heterogeneous attainment synthesis + gap_concentration |
| 19 | Ramp: effective capacity 85–90% | ✅ | **LANDED (M5 iter 4):** capacity block: headcount 98% of plan, ramp drag -> effective capacity 87% (m5i4s19) |
| 20 | Mix shift to higher-margin tiers post-guardrails | ✅ | **LANDED (M5 iter 3):** per-quarter discount-tier term + monotone blended-path shaping |
| 23 | Comp change  short-cycle small-deal behavior | ✅ | **LANDED (M5 iter 1):** medians_by_quarter per-period deal-size curves |
| 25 | 101% of plan via a few early outlier deals | ✅ | **LANDED (M5 iter 4):** mixture-aware raking exact: headline 101% vs ex-whale core 90% (m5i4s25b2) |
| 1 | Territory design + capacity + pipeline quality combo | ✅ | **LANDED (M5 iter 4):** combo: attainment miss + coverage + slippage trend + effective capacity 85% (m5i4s1) |
| 2 | Commit concentrated in no-engagement deals | ✅ | **LANDED (M5 iter 4):** forecast commit flags + activity: ~50% of commit value on zero-touch deals (m5i4s2) |
| 4 | Whitespace under-covered after capacity added | ✅ | **LANDED (M5 iter 4):** potential_coverage_gap +27.8pp under-coverage + placement on historical bookings (m5i4s4) |
| 5 | Forecast miss via slippage into next quarter | ✅ | **LANDED (M5 iter 3, s5):** P4 machinery + coverage plan sizing; AC4 thin-margin delivered via hardening-best |
| 9 | Expansion ↓ where AE ownership changed recently | ✅ | **LANDED (M5 iter 4):** ownership churn + post-change drag: changed-owner accounts -53% vs stable -4% (m5i4s9) |
| 10 | Capacity +10% but attainment −6pts (ramp placement) | ✅ | **LANDED (M5 iter 4):** headcount_growth_placement 100% to strong units + effective capacity lag (m5i4s10) |
| 11 | Pipeline decay: stale deals erode effective coverage | ✅ | **LANDED (M5 iter 3, s11q):** engine-exact staleness MC model + raking/open-value contract fix + coverage plan sizing |
| 13 | Activity ↑ but aimed at low-potential accounts | ✅ | **LANDED (M5 iter 4):** activity tilt: low-potential half receives +40pp over fair share of touches (m5i4s13) |
| 14 | Forecast +9% from overweighted expansion commit | ✅ | **LANDED (M5 iter 4):** forecast_snapshot: commit ran 109% of actual all year (m5i4s14) |
| 16 | Price elasticity varies by territory | ✅ | **LANDED (M5 iter 4):** pricing_response: +12.6pp conversion differential between potential halves (m5i4s16) |
| 17 | Beat driven by outliers masks leading-indicator decline | ✅ | **LANDED (M5 iter 4):** outlier share_by_quarter: headline +32.7% while core -59.7% (m5i4s17) |
| 21 | Open pipeline concentrated in few accounts | ✅ | **LANDED (M5 iter 3, s21d):** deal-size sigma solved by seeded MC order statistics + noise-aware slippage path solver |
| 22 | Rebalance capacity: expansion vs new-logo motions | ✅ | **LANDED (M5 iter 4):** quota.by_motion raking exact: Expansion 106%, New Logo 97% (m5i4s22) |
| 24 | Consolidation left strategic accounts unowned | ✅ | **LANDED (M5 iter 4):** account_ownership: 29% of top-value accounts unowned in H2 (m5i4s24) |

**Scorecard: 25/25 LANDED (v1 complete, 2026-08-25).**

---

## 2. Workstreams (dependency-ordered)

### WS1 — Planning Entity Layer *(highest leverage: alone flips most of 🟡)*
New entities the generator must support alongside accounts/opportunities:
- **Quota/plan table**: target revenue/bookings per segment × region × period (the number every scenario "misses" or "beats")
- **Territory model**: territory ↔ account membership, market potential score, AE assignment
- **Capacity model**: headcount per territory, ramp curves (new AEs produce at % of steady-state)

Requires: aggregate-targets primitive (WS3) so actuals can be steered relative to plan.

### WS2 — Product Dimension
Products entity: tier (entry/mid/strategic), margin %, COGS. Enables pricing-realization and product-mix narratives.

### WS3 — Aggregate Targets Primitive (raking)
Post-generation normalization pass: scale/steer row-level data until aggregate totals hit plan-relative targets (e.g., "Enterprise missed plan by 6%"). Driven by acceptance criteria, validated like any other criterion.

### WS4 — Correlation Primitive
Field-to-field conditioning: sample discount μ from a function of product margin, deal size, etc. (Gaussian copula or linear conditioning on log-fields).

### WS5 — Hierarchy / Random Effects
Per-group latent draws persisted across member rows: rep-level discount bias, account-level loyalty/penetration scores, territory productivity.

### WS6 — Open-Pipeline State Machine *(unlocks the entire 🔴 pipeline-quality cluster, incl. G5)*
Opportunities gain lifecycle: created → stages (aging timestamps per transition) → closed/open-at-snapshot. Enables stale-decay, effective-vs-reported coverage, slippage into next quarter, concentration analysis. Biggest single build on this list.

### WS7 — Temporal Entities
Ownership history (AE↔account assignments over time), engagement/activity fact table (meetings, touches), forecast snapshots (commit vs actual over time), customer product-penetration records.

### WS8 — Distribution Extensions (small, incremental)
- Period-varying categorical weights (mix shifts between quarters)
- Per-period deal-size curve parameters
- Mixture/outlier component (a few whale deals vs the population)
- Prior-year history option (LQ/L4Q comparisons)

---

## 3. Suggested Sequencing

```
WS3 (raking) ──┐
WS1 (planning) ─┼──> unlocks scenarios 3,6,7,12,15,18,19 (+partial others)
WS8 (small exts)┘
WS2 (products) + WS4 (correlation) ──> 8, 20, 23 completed
WS5 (hierarchy) ──> 18 completed fully, foundations for WS7
WS6 (state machine) ──> 1, 5, 11, 21 (pipeline-quality cluster)
WS7 (temporal) ──> 2, 4, 9, 13, 14, 22, 24 (needs WS5 + WS6 first)
WS16-analog (demand model) ──> 16, 17 last (research-flavored)
```

Rationale: WS3+WS1 are cheap and flip the biggest count. WS6 is the largest single build and gates the hardest cluster. WS7 depends on both hierarchy (stable identities) and the state machine (temporal spine).

---

## 4. V1 Exit Criteria

1. All 25 scenarios landable end-to-end via `syngen new` with signed-off acceptance criteria.
2. Each new primitive follows the experiment discipline: isolated proof on ONE story before generalization (B→D pattern).
3. Determinism, black-box validation, and two human gates preserved throughout — no capability may bypass the architecture contracts.
4. Performance expectations remain honest: complex scenarios will take longer (more entities, more criteria); document per-cluster latency as they land.
