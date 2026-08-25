# SynGen RevOps Entity Schema — Review Draft

> **Status:** REVIEW DRAFT (2026-08-25, M6 P1 entry step). This document
> organizes the RevOps domain pack using the canonical taxonomy structure
> (`Type | Entity | Role`), extended with Planning/Capacity-facts and
> History/State sections. Every physical schema below is transcribed from
> the implemented engine (`syngen/generator/engine.py`) and validation
> contract (`syngen/linter.py`); nothing is aspirational except where
> explicitly marked. Supersedes `DATA_MODEL.md` §1 (stale v0 diagram).
>
> **Review ask:** does this capture real-world RevOps business taxonomy?
> Column choices, grain decisions, derived-field rules, and KPI definitions
> are all fair game. After sign-off these tables become machine-readable
> `packs/revops/entities/*.json` enforced by the pack loader.

---

## 1. Naming conventions

| Convention | Rule | Examples |
|---|---|---|
| Primary keys | `<entity>_id`, prefixed sequence | `ACC-0001`, `OPP-00001`, `REP-0004` |
| Foreign keys | exact name of referenced PK | `account_id` → `accounts.account_id` |
| Lifecycle | ONE canonical status field per entity | `stage` on opportunities |
| Denormalization | dimension values copied onto fact tables deliberately so consumers aggregate without joins | `region`, `segment`, `icp` on opportunities |
| Derived fields | computed at generation time from siblings, never sampled independently | `realized_price` |
| Plan sheets | unified `plan_unit_type` + `plan_unit` naming keeps checks domain-neutral | `quota_plan`, `capacity_plan` |
| Percent fields | suffix `_pct`; USD amounts suffix `_usd` | `discount_pct`, `target_realized_usd` |

---

## 2. Canonical taxonomy

Adapted from the original v1 taxonomy; two sections added (Planning facts,
History & State). Status: ✅ built · 🟡 partial · ❌ not built (v1 boundary).

| Type | Entity | Role | Status | Artifact(s) |
|---|---|---|---|---|
| **Core business entity** | Account | Customer/company | ✅ | `accounts` sheet |
| | Opportunity | Sales pursuit | ✅ | `opportunities` sheet |
| | Rep | Commercial actor | ✅ | `reps` sheet |
| | Product | What is sold | 🟡 | columns on `opportunities` |
| **GTM dimensions** | Territory | Where / coverage | ✅ | `territory` column + rollups |
| | Segment | Who / market classification | ✅ | `segment` column |
| | Route to Market | How we sell | ❌ | — |
| | Revenue Motion | Why/how the commercial motion occurs (New Logo / Expansion) | ✅ | `motion` column via `quota.by_motion` |
| **Time dimension** | Time Period | When | ✅ | `time_model` block + `fiscal_quarter` columns |
| **Performance / planning** | Quota | Expected performance | ✅ | `quota` block + `quota_plan` sheet |
| | Compensation | Incentive mechanism | ❌ | — |
| **Planning & Capacity facts** *(added)* | Capacity Plan | Headcount plan vs actual with ramp drag | ✅ | `capacity` block + `capacity_plan` sheet |
| **Activity / transaction** | Opportunity Activity | What happened during pursuit (touches) | ✅ | `activity` block + `account_activity` sheet |
| | Booking | Commercial outcome | 🟡 implicit | won opportunities ARE bookings |
| **History & State** *(added)* | Stage History | Opportunity progression through open stages | ✅ | `opportunity_stage_history` sheet |
| | Ownership History | Dated rep-account assignment | ✅ | `account_ownership` sheet |
| | Forecast Snapshot | Commit vs actual at period grain | ✅ | `forecast_snapshot` sheet |
| **Derived analytics** | Whitespace | Potential minus current penetration | 🟡 | `market_potential_usd` + checks |
| | Product Penetration | Account × Product measure | ❌ | — |
| | Revenue KPIs | See §6 KPI registry | ✅ | validator check library |

---

## 3. Entity schemas

### 3.1 `accounts` — mandatory

**Grain:** one row per selling account. Snapshot only — no slowly-changing
dimensions at v1 scale.

| Column | Type | Required | Semantics |
|---|---|---|---|
| `account_id` | id PK | ✔ | `ACC-nnnn` |
| `account_name` | string | ✔ | generated display name (industry + suffix) |
| `region` | categorical | ✔ | e.g. AMER / EMEA / APAC (config weights) |
| `segment` | categorical | ✔ | e.g. Enterprise / Mid-Market / SMB / CSB |
| `industry` | categorical | ✔ | sampled industry pool |
| `market_potential_usd` | decimal | ✔ | addressable potential; uniform draw, optional per-territory/per-region overrides (affine remap, rank-preserving) |
| `icp` | boolean | ✔ | ideal-customer-profile flag (share knob) |
| `territory` * | categorical | block | present when `accounts.territories` maps regions→territories; a region MAY split across territories |

### 3.2 `opportunities` — mandatory

**Grain:** one row per opportunity created inside the simulation window.
Lifecycle lives on the row: terminal rows carry `close_date` + won/lost
stage; open-pipeline rows carry an open stage, null `close_date`, and a
revised `expected_close_date`.

| # | Column | Type | Required | Semantics |
|---|---|---|---|---|
| 1 | `opportunity_id` | id PK | ✔ | `OPP-nnnnn`, globally sequential |
| 2 | `account_id` | fk | ✔ | → `accounts.account_id` |
| 3 | `owner` | string | ✔ | rep name pool; respects ownership history when present |
| 4 | `region` | categorical | ✔ | denormalized from account |
| 5 | `segment` | categorical | ✔ | denormalized |
| 6 | `icp` | boolean | ✔ | denormalized |
| 7 | `fiscal_quarter` | categorical | ✔ | FY26-Qn label (config calendar may differ) |
| 8 | `created_date` | date | ✔ | close date − duration draw |
| 9 | `close_date` | date | ✔* | within quarter; NULL while open |
| 10 | `expected_close_date` * | date | block | pipeline block; inserted adjacent to `close_date`; slips past quarter-end per slip-rate knobs |
| 11 | `stage` | categorical | ✔ | `Closed Won` / `Closed Lost` terminal; open stages from pipeline block config |
| 12 | `list_price` | decimal | ✔ | lognormal median/sigma knobs; whale multiplier applied to outliers |
| 13 | `discount_pct` | decimal | ✔ | effect-driven curve (group×period, window boost, noise) |
| 14 | `realized_price` | decimal | ✔ | DERIVED: `list_price × (1 − discount_pct/100)` |
| 15 | `territory` * | categorical | block | territories block; emitted before product columns |
| 16 | `product_id` * / `product_tier` * / `cogs_ratio` * | id/cat/decimal | block | products block attribution trio |
| 17 | `motion` * | categorical | block | quota.by_motion; derived chronologically: first deal per account = New Logo, later = Expansion |
| 18 | `in_commit` * | boolean | block | forecast block; share of WON deals flagged as org commit, optional bias toward zero-touch accounts |
| 19 | `is_outlier` * | boolean | block | outlier_deals block; persistent replay of the whale selection stream |

Column order matters: insertion order defines workbook sheet columns.

### 3.3 `quota_plan` — when `quota` block present

**Grain:** one row per plan unit × fiscal quarter.

| Column | Type | Required | Semantics |
|---|---|---|---|
| `plan_unit_type` | categorical | ✔ | `segment` \| `territory` \| `motion` — names the grouping dimension |
| `plan_unit` | string | ✔ | value of that dimension |
| `fiscal_quarter` | categorical | ✔ | |
| `target_realized_usd` | decimal | ✔ | the plan actuals are raked/measured against |

### 3.4 `reps` — when `capacity` block present

**Grain:** one row per rep ever on staff during the window (initial cohort +
net hires; attrition not modeled).

| Column | Type | Required | Semantics |
|---|---|---|---|
| `rep_id` | id PK | ✔ | `REP-nnnn` |
| `rep_name` | string | ✔ | name pool |
| `region` \| `territory` | categorical | ✔ | capacity plan dimension (exactly one) |
| `hire_fiscal_quarter` | categorical | nullable | NULL = tenured before the window |

### 3.5 `capacity_plan` — when `capacity` block present

**Grain:** one row per plan unit × fiscal quarter.

| Column | Type | Required | Semantics |
|---|---|---|---|
| `fiscal_quarter` | categorical | ✔ | |
| `plan_unit_type` / `plan_unit` | categorical/string | ✔ | same convention as quota_plan |
| `headcount_plan` | int | ✔ | what the annual plan assumed (fully productive) |
| `headcount_actual` | int | ✔ | staffed reality |
| `ramping_reps` | int | ✔ | hires still below full productivity |
| `ramp_productivity_pct` | decimal | ✔ | ramp curve assumption |
| `effective_capacity_pct` | decimal | ✔ | DERIVED: `((actual − ramping) + ramping × ramp_pct/100) ÷ plan × 100` — where "98% staffed but 85–90% effective" stories live |

### 3.6 `account_ownership` — when `ownership` block present

**Grain:** one row per account × fiscal quarter (dated rep-account
assignment).

| Column | Type | Required | Semantics |
|---|---|---|---|
| `account_id` | fk | ✔ | |
| `fiscal_quarter` | categorical | ✔ | |
| `owner` | string | ✔ | drives opportunity `owner`; changes feed post-change analyses |

### 3.7 `account_activity` — when `activity` block present

**Grain:** one row per account × fiscal quarter.

| Column | Type | Required | Semantics |
|---|---|---|---|
| `account_id` | fk | ✔ | |
| `fiscal_quarter` | categorical | ✔ | |
| `touches` | int | ✔ | Poisson draws with optional potential-tilt factor |

### 3.8 `opportunity_stage_history` — when `pipeline` block present

**Grain:** one row per open-stage entry event (open pipeline cohort per
quarter).

| Column | Type | Required | Semantics |
|---|---|---|---|
| `opportunity_id` | fk | ✔ | |
| `stage` | categorical | ✔ | open stage at evaluation time |
| `entered_date` | date | ✔ | opportunity creation date |
| `fiscal_quarter` | categorical | ✔ | quarter the stage was entered |

### 3.9 `forecast_snapshot` — when `forecast` block present

**Grain:** one row per fiscal quarter, organization-wide.

| Column | Type | Required | Semantics |
|---|---|---|---|
| `fiscal_quarter` | categorical | ✔ | |
| `committed_usd` | decimal | ✔ | the story's claim: actual × commit_ratio (plan-like semantics) |
| `actual_usd` | decimal | ✔ | measured from won-deal `realized_price` sums |
| `commit_vs_actual_pct` | decimal | ✔ | DERIVED: `committed ÷ actual × 100` |

### 3.10 `quarterly_summary` — always present (derived view)

**Grain:** one row per fiscal quarter. Computed from fact rows ONLY — never
authored independently; never an input to validation (validator recomputes
from raw rows).

| Column | Type | Definition |
|---|---|---|
| `fiscal_quarter` | categorical | |
| `opportunities` | int | count all |
| `closed_won` | int | count stage = Closed Won |
| `win_rate_pct` | decimal | won ÷ total × 100 |
| `avg_discount_won_pct` | decimal | mean discount of won |
| `realized_vs_list_pct` | decimal | Σrealized ÷ Σlist × 100 (won) |
| `total_realized_usd` | decimal | Σ realized (won) |

### 3.11 `_synngen_meta` — always present

Seed, config hash, generation timestamp, criteria version (provenance
contract, ARTIFACT_CONTRACTS A8).

---

## 4. Block × optional artifact matrix

| Config block | Sheet(s) added | Columns added to `opportunities` |
|---|---|---|
| *(none — baseline)* | accounts, opportunities, quarterly_summary, _synngen_meta | — |
| `accounts.territories` | — | `territory` |
| `products` | — | `product_id`, `product_tier`, `cogs_ratio` |
| `pipeline` | `opportunity_stage_history` | `expected_close_date` |
| `quota` (+`by_motion`) | `quota_plan` | `motion` |
| `capacity` | `reps`, `capacity_plan` | — |
| `ownership` | `account_ownership` | (influences `owner` assignment) |
| `activity` | `account_activity` | — |
| `forecast` | `forecast_snapshot` | `in_commit` |
| `opportunities.outlier_deals` | — | `is_outlier` |

---

## 5. Derived-field rules

| Field | Formula | Enforcement |
|---|---|---|
| `realized_price` | `list_price × (1 − discount_pct/100)` | generation-time compute; independent sampling is a sanity violation |
| `commit_vs_actual_pct` | `committed_usd ÷ actual_usd × 100` | snapshot build |
| `effective_capacity_pct` | `((actual − ramping) + ramping × ramp_pct/100) ÷ plan × 100` | capacity build |
| `motion` | chronological seen-set per account: first deal New Logo, later Expansion | pre-raking derive when plan dimension is motion |
| summary views | aggregates over fact rows only | black-box rule: validator never reads summaries |

---

## 6. KPI registry (derived metrics)

Each KPI: canonical definition (plain formula, expert-readable) plus its
bound proof-check id. Parameterized variants noted where the implementation
uses bands/thresholds.

### Win/Loss & Volume

| KPI | Definition | Bound check |
|---|---|---|
| Win Rate | won ÷ closed, per period/cohort | `win_rate_flat` (stability band) |
| Creation Volume | opportunities created per period | `creation_volume_trend` (direction) |
| Deal Size | mean/median realized value | `deal_size_trend` (direction) |
| Revenue Concentration | share of revenue held by top-x accounts | `revenue_concentration` (≥ threshold) |

### Pricing, Discount & Margin

| KPI | Definition | Bound check |
|---|---|---|
| Average Discount | mean discount per period/cohort | `avg_discount_quarter` (level band) |
| Discount Trend | period-over-period discount direction | `discount_trend_monotonic` (monotonicity) |
| Regional Price Premium | discount/price differential by region | `region_discount_premium` (≥ pp gap) |
| Realized vs List | Σrealized ÷ Σlist | `realized_vs_list` (band) |
| Price by Tier | mean price per product tier | `avg_price_by_tier` (ordering/band) |
| Discount↔Margin Link | correlation(discount, margin) | `discount_margin_link` (strength band) |
| Blended Margin | (realized − cogs)/realized, blended | `blended_margin_trend` (direction) |
| Elasticity Differential | discount-response difference between cohorts | `elasticity_differential` (≥ pp differential) |
| End-of-Quarter Effect | close-date clustering near period end | `end_of_quarter_effect` (window share) |

### Pipeline Health

| KPI | Definition | Bound check |
|---|---|---|
| Pipeline Coverage | open pipeline ÷ next-period quota target | `coverage_ratio` (multiple band) |
| Sales Cycle | close_date − created_date | `cycle_length_trend` (direction) |
| Stage Aging | age distribution across open stages | `stage_aging` (shape/threshold) |
| Slippage Rate | share of open deals whose expected_close passes quarter end | `slippage_trend` (direction) |
| Pipeline Concentration | open-pipeline share held by top accounts | `pipeline_concentration` (threshold) |

### Planning & Capacity Attainment

| KPI | Definition | Bound check |
|---|---|---|
| Plan Attainment | actual ÷ target per plan unit × period | `revenue_vs_plan` (band, raked) |
| Effective Capacity | see §5 derived field | `effective_capacity` (band around 100%) |
| Headcount Growth Placement | Δheadcount located where bookings are | `headcount_growth_placement` (correlation/rank) |
| Unowned Share | accounts without current owner | `unowned_account_share` (≤ threshold) |
| Quota vs Potential | target ÷ market_potential per unit | `quota_vs_potential` (ratio band) |

### Whitespace & Penetration

| KPI | Definition | Bound check |
|---|---|---|
| Potential Coverage Gap | pipeline reach into high-potential accounts | `potential_coverage_gap` (gap threshold) |
| Gap Concentration | whitespace concentrated in bottom-x% territories/accounts | `gap_concentration` (share threshold) |

### Forecast Integrity

| KPI | Definition | Bound check |
|---|---|---|
| Forecast vs Actual | commit ÷ actual per period | `forecast_vs_actual` (band ±pp; direction-aware) |
| Commit Engagement | commit deals on zero-touch accounts | `commit_no_engagement_share` (share threshold) |
| Core vs Headline Growth | ex-outlier growth vs total growth | `core_vs_headline_growth` (divergence ≥ pp) |

### Ownership & Activity

| KPI | Definition | Bound check |
|---|---|---|
| Post-Change Revenue | revenue trajectory after ownership change | `post_change_revenue_decline` (drop ≥ pp/pct) |
| Activity-Potential Alignment | touch tilt vs market potential | `activity_potential_misalignment` (pp misalignment) |

---

## 7. Declared vocabulary gaps

Claims observed in UAT stories that NO current check proves. These are
named roadmap entries, not failures (DOMAIN_PACKS.md graduated policy):

| Gap | Requested by | Family |
|---|---|---|
| `stage_distribution_share` — early-stage share of committed/open pipeline, per period | scenario_05, F6.1 | pipeline health |
| `cohort_revenue_trend` — per-cohort revenue direction across periods | scenario_17, F5.2 | volume |
| dead-deal composite (stalled ∧ inactive ∧ aging) | scenario_02, F7.2 | pipeline health |
| forecast-vs-commit divergence (commit flags vs snapshot claims) | scenario_05, F7.2 | forecast integrity |
| portfolio composition (mature vs new-logo account mix per AE) | scenario_04, F9.2 | account expansion |
| Conversion Rate (MQL→SQL→Opp→Booking progression) | expanded taxonomy | lifecycle (needs marketing ops) |
| Pipeline Velocity (pipeline × win rate × deal size ÷ cycle) | expanded taxonomy | pipeline health |

---

## 8. Out-of-scope register (v1 boundary)

Recorded, not designed: Contacts/Person, Opportunity Line Items, Booking
Line Items, Contract/Order, Subscription, Recognized Revenue, Comp Plans &
Commission Outcomes, Campaign/Lead/MQL/SQL and all marketing analytics,
Account Lifecycle events (Renewal/Expansion/Churn as separate entities),
Route to Market, ARR/MRR/GRR/NRR metrics. Source taxonomy retains them for
post-v1 packs; scope decision recorded in `CANONICAL_MODEL.md`.
