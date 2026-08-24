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
| 3 | SMB beat plan, entry-price mix, discount creep | 🟡 | Escalated once - drafter drew contradictory deal_size_trend-under-raking criterion + missed SMB attainment knob; volume-under-raking playbook fix landed after |
| 6 | Ent missed / MM beat via quota-vs-potential mismatch | ✅ | **LANDED (M4):** quota block + raking + revenue_vs_plan; market_potential_usd on accounts (WS1-lite) |
| 7 | Bookings -3%, pipeline creation +12% (low-ICP mix) | ✅ | **LANDED (M5 iter 1):** icp_share + icp_sampling_weights_by_quarter + deal_size_trend + icp_creation_shift |
| 8 | COGS↑, discounts concentrated in high-margin products | 🟡 | Primitives shipped + live-verified individually; escalated 4× on drafter draw variance (coupling calculus now in playbook; pre-flight calibration is next theme) |
| 12 | Comp plan → entry-tier deals + discounting, margin ↓ | ✅ | **LANDED (M5 iter 2):** products block + blended_margin_trend + tier_share_shift + avg_price_by_tier; 5/5 certified |
| 15 | Quotas 20–25% above addressable market | 🟡 | WS1 quota/potential ratio entities |
| 18 | Gap concentrated in bottom-quartile territories | 🟡 | WS5 territories + gap_concentration check + quota by_territory shipped and unit-tested; live run deferred to iter 3 |
| 19 | Ramp: effective capacity 85–90% | 🟡 | WS1 capacity table + ramp curves |
| 20 | Mix shift to higher-margin tiers post-guardrails | 🟡 | tier_share_shift + weights_by_quarter shipped and unit-tested (landed within #12 run); standalone live run deferred to iter 3 |
| 23 | Comp change  short-cycle small-deal behavior | ✅ | **LANDED (M5 iter 1):** medians_by_quarter per-period deal-size curves |
| 25 | 101% of plan via a few early outlier deals | 🟡 | PARTIAL (M5 iter 1): outlier_deals + revenue_concentration + _all_ attainment land; ex-whale underlying attainment needs mixture-aware raking (Iter 4, with WS8 mixtures) |
| 1 | Territory design + capacity + pipeline quality combo | 🔴 | WS6 stages/aging + WS1 territories/capacity |
| 2 | Commit concentrated in no-engagement deals | 🔴 | WS7 engagement signals + forecast snapshots |
| 4 | Whitespace under-covered after capacity added | 🔴 | WS1 territory/account potential model |
| 5 | "Commit" loosened; deals slipped next quarter | 🔴 | WS6 open-pipeline state machine (G5) |
| 9 | Expansion ↓ where AE ownership changed recently | 🔴 | WS7 temporal ownership + product penetration |
| 10 | Capacity +10% but attainment −6pts (ramp placement) | 🔴 | WS1 headcount placement model |
| 11 | Pipeline decay/stale opps → effective coverage | 🔴 | WS6 open-pipeline state machine (G5) |
| 13 | Activity ↑ but aimed at low-potential accounts | 🔴 | WS7 activity/meetings fact table |
| 14 | Forecast +9% from overweighted expansion commit | 🔴 | WS7 forecast snapshot entity |
| 16 | Price elasticity varies by territory | 🔴 | New demand/volume-response model |
| 17 | Beat driven by outliers masks leading-indicator decline | 🔴 | WS8 mixtures + leading-indicator fields |
| 21 | Coverage 3.5x but concentrated (original moonshot) | 🔴 | WS6 open pipeline + concentration metrics |
| 22 | Rebalance capacity: expansion vs new-logo motions | 🔴 | WS7 customer penetration + motion classification |
| 24 | Consolidation left strategic accounts unowned | 🔴 | WS7 temporal ownership rules |

**Scorecard: 0 today · 11 within planned primitives · 14 need structural (process/state) work.**

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
