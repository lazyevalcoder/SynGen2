"""Kernel shim for the RevOps check library (M6 P3).

The checks physically live in the domain pack now
(`syngen/packs/revops/checks.py`); this module keeps every historical
import path working (`from syngen.validator.checks import CHECKS`). The
pack is the single source of truth - do not add checks here.
"""
from syngen.packs.revops.checks import (  # noqa: F401
    CHECKS,
    QUARTER_ENDS,
    _margin_pct,
    check_activity_potential_misalignment,
    check_avg_discount_quarter,
    check_avg_price_by_tier,
    check_blended_margin_trend,
    check_commit_no_engagement_share,
    check_core_vs_headline_growth,
    check_coverage_ratio,
    check_creation_volume_trend,
    check_cycle_length_trend,
    check_data_sanity,
    check_deal_size_trend,
    check_discount_margin_link,
    check_discount_trend_monotonic,
    check_effective_capacity,
    check_elasticity_differential,
    check_end_of_quarter_effect,
    check_forecast_vs_actual,
    check_gap_concentration,
    check_headcount_growth_placement,
    check_icp_creation_shift,
    check_pipeline_concentration,
    check_potential_coverage_gap,
    check_post_change_revenue_decline,
    check_quota_vs_potential,
    check_realized_vs_list,
    check_revenue_concentration,
    check_revenue_vs_plan,
    check_region_discount_premium,
    check_slippage_trend,
    check_stage_aging,
    check_tier_share_shift,
    check_unowned_account_share,
    check_win_rate_flat,
    quarter_start,
    resolve_quarter_ends,
    won_deals,
)
