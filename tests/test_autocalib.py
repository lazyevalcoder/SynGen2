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
