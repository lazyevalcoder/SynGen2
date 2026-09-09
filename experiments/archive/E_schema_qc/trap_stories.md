# Trap Stories — Schema QC

## T1 — Synonym duplication trap
> Our sales team tracked opportunities through the pipeline all year. Deals that closed in Q4 carried noticeably deeper discounts than those closed earlier in the year. Deal-level analysis shows the discount creep was concentrated in EMEA accounts.

Induces: model may create BOTH an `opportunities` table AND a `deals` table (synonyms for the same grain).

## T2 — Stored-aggregate trap
> Average win rate by quarter held at 27%, while average discount by quarter and region climbed steadily. Quarterly revenue totals by region show margins compressing every quarter.

Induces: model may create `quarterly_metrics` / `region_quarterly_summary` as STORED tables rather than derived views.

## T3 — Incomplete-taxonomy trap
> Enterprise deals were over-allocated relative to pipeline targets, while Mid-Market was under-allocated. Discounting behavior diverged sharply between the two segments in H2.

Induces: model assumes only {Enterprise, Mid-Market} exist, dropping SMB/CSB from the real-world taxonomy.

## CONTROL — Validated discount-erosion story
> Win rates held steady this year, but average deal discounts crept up from 12% to 18%, quietly eroding margins. The bleed is worst in EMEA, where reps are discounting aggressively to close end-of-quarter deals.

Expected: clean spec, no lint violations beyond advisory notes.
