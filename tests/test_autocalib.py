"""Auto-calibration tests: pinned levels and tier shares are solved
deterministically, not drafted."""
import copy

import sys
sys.path.insert(0, ".")
from tests.test_preflight import base_cfg, crit, PRODUCTS  # noqa: E402

from syngen.phases.preflight import autocalibrate, calibrate, hard_findings


def test_autocalibrate_fixes_realized_vs_list_level():
    cfg = base_cfg()
    doc = crit("realized_vs_list", quarter_start="FY26-Q1",
               target_start_pct=90, quarter_end="FY26-Q4",
               target_end_pct=82, tolerance_pp=2)
    fixes = autocalibrate(cfg, doc)
    assert 1 <= len(fixes) <= 2, fixes
    findings = calibrate(cfg, doc)
    assert not [f for f in findings if f["rule"] == "PF2"], findings


def test_autocalibrate_solves_tier_share_targets():
    cfg = base_cfg(products={
        "catalog": [
            {"id": "E", "tier": "entry", "share": 0.3},
            {"id": "C", "tier": "core", "share": 0.5},
            {"id": "P", "tier": "premium", "share": 0.2},
        ],
        "margin_by_tier": {"entry": 0.45, "core": 0.6, "premium": 0.75},
        "price_multiplier_by_tier": {"entry": 0.4, "core": 1.0,
                                     "premium": 2.5},
    })
    # entry at 40% count share x 0.4 mult vs (50x1 + 20x2.5=100)... solve
    doc = crit("tier_share_shift", tier="entry", from_share_pct=10,
               to_share_pct=30, tolerance_pp=3)
    fixes = autocalibrate(cfg, doc)
    assert len(fixes) == 2, fixes
    hard = hard_findings(calibrate(cfg, doc))
    assert not hard, hard
    from syngen.phases.preflight import _tier_revenue_shares_at
    s1 = _tier_revenue_shares_at(cfg, 0)["entry"] * 100
    s4 = _tier_revenue_shares_at(cfg, 3)["entry"] * 100
    assert abs(s1 - 10) < 1.5 and abs(s4 - 30) < 1.5, (s1, s4)


def test_autocalibrate_avg_discount_quarter():
    cfg = base_cfg()
    doc = crit("avg_discount_quarter", quarter="FY26-Q3", target_pct=20,
               tolerance_pp=2)
    fixes = autocalibrate(cfg, doc)
    assert len(fixes) == 1
    soft = [f for f in calibrate(cfg, doc) if f["rule"] == "PF2"]
    assert not soft


# ---- F25: exact staleness model + coverage-aware plan sizing ----

def test_stale_probs_match_engine_within_tolerance():
    """The Monte-Carlo stale model must replicate what the ENGINE
    actually produces (within sampling noise) - this is the property
    whose absence caused the s11 escalations."""
    import numpy as np
    from tests.test_iter3 import base_cfg as pbase, PIPE, make_engine_data
    from syngen.phases.preflight import _pipeline_stale_probs
    pipe = dict(PIPE, share_open_by_quarter=[0.2, 0.25, 0.3, 0.35])
    cfg = pbase(pipeline=pipe)
    opp = make_engine_data(cfg)
    open_rows = opp[~opp["stage"].isin(["Closed Won", "Closed Lost"])]
    ref = __import__("pandas").Timestamp("2026-12-31")
    ages = (ref - __import__("pandas").to_datetime(
        open_rows["created_date"])).dt.days
    thr = 90
    actual = float((ages > thr).mean())
    probs = _pipeline_stale_probs(cfg, float(thr))
    pred = sum(s * p for s, p in zip(pipe["share_open_by_quarter"], probs)) \
        / sum(pipe["share_open_by_quarter"])
    assert abs(actual - pred) < 0.04, (actual, pred)


def test_solve_open_shares_meets_cap_or_best_effort():
    from syngen.phases.preflight import _solve_open_shares
    # all mass early, all early quarters fully stale -> tilt hard
    shares = [0.55, 0.25, 0.15, 0.05]
    probs = [0.95, 0.7, 0.15, 0.02]
    new = _solve_open_shares(shares, probs, cap=0.35)
    assert new is not None
    blend = sum(s * p for s, p in zip(new, probs)) / sum(new)
    assert blend <= 0.35 * 0.85 + 1e-3, (blend, new)
    # floors hold: no quarter loses more than ~75% of its relative weight
    for o, v in zip(shares, new):
        assert v >= 0.2 * o / sum(shares) - 1e-6, (o, v)
    # already-compliant config untouched
    assert _solve_open_shares([0.1, 0.2, 0.3, 0.4],
                              [0.01, 0.05, 0.1, 0.2], 0.35) is None


def test_coverage_scales_plan_down_to_multiple():
    cfg = base_cfg(pipeline={
        "stage_names": ["Discovery", "Proposal"],
        "share_open_by_quarter": [0.25, 0.25, 0.25, 0.25],
        "slippage_rate_by_quarter": [0.1, 0.1, 0.1, 0.1],
    })
    n_q = len(cfg["time_model"]["quarter_labels"])
    natural = (cfg["opportunities"]["per_quarter"]
               * cfg["opportunities"]["win_rate"]
               * float(cfg["opportunities"]["deal_size_lognormal"]
                       ["median_usd"]) * 0.85)
    cfg["quota"] = {
        "by_segment": {"Enterprise": [natural] * n_q,
                       "SMB": [natural] * n_q},
        "attainment": {}}
    doc = crit("coverage_ratio", quarter="FY26-Q2", min_multiple=3)
    fixes = autocalibrate(cfg, doc)
    assert any("coverage" in f or "plan" in f.lower() for f in fixes), fixes
    total_q2 = sum(float(u[1]) for u in cfg["quota"]["by_segment"].values())
    assert total_q2 < natural * 2  # scaled below the old level
    # revenue_vs_plan ratios unaffected: attainment untouched
    assert cfg["quota"]["attainment"] == {}


def test_coverage_ignores_out_of_range_offset():
    cfg = base_cfg()
    doc = crit("coverage_ratio", quarter="FY26-Q1",
               target_quarter_offset=-1, min_multiple=3)
    fixes = autocalibrate(cfg, doc)  # no pipeline/quota at all: no-op
    assert not [f for f in fixes if "coverage" in f]


def test_repair_criteria_drops_offset_outside_calendar():
    from syngen.phases.preflight import repair_criteria
    cfg = base_cfg()
    doc = crit("coverage_ratio", quarter="FY26-Q1",
               target_quarter_offset=-1, min_multiple=3)
    notes = repair_criteria(cfg, doc)
    assert len(notes) == 1
    assert "target_quarter_offset" not in doc["criteria"][0]["params"]
    # in-range offsets are untouched
    doc2 = crit("coverage_ratio", quarter="FY26-Q2",
                target_quarter_offset=-1, min_multiple=3)
    assert not repair_criteria(cfg, doc2)


def test_stage_aging_infeasible_cap_shortens_durations():
    from syngen.phases.preflight import _pipeline_stale_probs
    cfg = base_cfg(pipeline={
        "stage_names": ["Discovery"],
        "share_open_by_quarter": [0.3, 0.3, 0.2, 0.2],
        "slippage_rate_by_quarter": [0.0, 0.0, 0.0, 0.0],
    })
    cfg["opportunities"]["deal_duration_days"] = [60, 95]
    doc = crit("stage_aging", stale_threshold_days=90,
               max_stale_share_pct=35)
    fixes = autocalibrate(cfg, doc)
    dd = cfg["opportunities"]["deal_duration_days"]
    assert dd[1] < 95, fixes          # shortened
    probs = _pipeline_stale_probs(cfg, 90.0)
    shares = cfg["pipeline"]["share_open_by_quarter"]
    blend = sum(s * p for s, p in zip(shares, probs)) / sum(shares)
    assert blend <= 0.40, (blend, shares, dd)


def test_coverage_clamps_all_quarters_to_open_value():
    cfg = base_cfg(pipeline={
        "stage_names": ["Discovery"],
        "share_open_by_quarter": [0.25, 0.25, 0.25, 0.25],
        "slippage_rate_by_quarter": [0.0] * 4,
    })
    n_q = len(cfg["time_model"]["quarter_labels"])
    huge = 18_000_000
    cfg["quota"] = {"by_segment": {"Enterprise": [huge] * n_q},
                    "attainment": {}}
    doc = crit("coverage_ratio", quarter="FY26-Q1", min_multiple=2)
    fixes = autocalibrate(cfg, doc)
    vals = cfg["quota"]["by_segment"]["Enterprise"]
    assert all(v < huge for v in vals), vals   # every quarter clamped
    assert any(fixes)
