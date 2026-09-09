# SynGen Canonical RevOps Model (Option A adoption)

Adopted 2026-08-24 as the **target architecture for the remaining M5
phases**. Not a refactor: existing denormalized columns stay; new
machinery is built as canonical entities instead of accreting more
columns. This document doubles as the interface spec for the post-v1
Domain Packs workstream (ROADMAP "Post-v1").

## Scope decision

Only the 🔵 Essential rows of the v1 canonical table are in scope for
v1. The expanded marketing-ops model (leads, campaigns, touches,
MQL/SQL, attribution) and finance-adjacent entities (contracts,
subscriptions, recognized revenue) are recorded in the source file
(`JUNK_NOT_PROJECT_RELATED/revops domain packs.txt`) and belong to the
unscheduled Domain Packs workstream. Line items / contacts are NOT
built - no scenario among the 25 demands them.

## Coverage map

| Canonical entity | v1 status | Where it lives |
|---|---|---|
| Account | ✅ built | `accounts` sheet + config block |
| Segment | ✅ built | accounts dimension |
| Territory | ✅ built (iter 2) | territory rollup, quota by_territory |
| Time Period | ✅ built | `time_model` + quarter sheets |
| Quota | ✅ built | `quota` block + `quota_plan` sheet |
| Product | 🟡 columns | product_id/tier/cogs_ratio on opportunities (iter 2); standalone catalog sheet only if a scenario demands it |
| Opportunity | 🟡 closed facts only | won/lost fact rows; **lifecycle lands in Iter 3 (P4)** |
| Rep | ✅ built (iter 4) | `reps` roster + `capacity_plan` sheet (WS1 rest) |
| Revenue Motion | ✅ built (iter 4) | `motion` column via quota.by_motion (#22) |
| Booking | implicit | won opportunities ARE bookings; separate booking facts only if a scenario demands them |
| Activity | ✅ built (iter 4) | `account_activity` fact table, touches per account x quarter (#13) |
| Stage History | ✅ built | Iter 3 (P4): open-pipeline state machine (#5/#11/#21) |
| Forecast snapshot | ✅ built (iter 4) | `forecast_snapshot` sheet + `in_commit` flags (#14/#2) |
| Ownership history | ✅ built (iter 4) | `account_ownership`, dated rep-account ownership (#9/#24) |
| Penetration / Whitespace | 🟡 partial | market_potential_usd on accounts + potential_coverage_gap check; deeper views when landing demands |

## Rule going forward

When an M5 phase introduces machinery that matches a canonical entity,
it MUST use the canonical name and shape (sheet/column naming above),
not a local synonym. When it doesn't match any canonical entity, keep
it minimal and note the divergence here.

**Update (2026-08-25, M6):** the column-level physical schema for every
entity now lives in `ENTITY_SCHEMA.md` (review draft, structured by the
canonical taxonomy). After expert sign-off it is transcribed into
`packs/revops/entities/*.json`; this file remains the conceptual
coverage map.
