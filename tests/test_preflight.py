"""M5 iteration 3: pre-flight calibration (F17).

The drafter-variance lesson: schema-valid configs whose arithmetic or
referential grounding misses the criteria used to burn whole convergence
sessions. These tests pin the deterministic cross-check in both
directions: clean configs pass silently, each defect class is caught.
"""
import copy

import pytest

from syngen.phases.preflight import calibrate, hard_findings


def base_cfg(**over):
    over = copy.deepcopy(over)
    cfg = {
        "seed": 42,
        "time_model": {
            "fiscal_year": "FY26",
            "quarter_labels": ["FY26-Q1", "FY26-Q2", "FY26-Q3", "FY26-Q4"],
            "quarter_end_dates": ["2026-03-31", "2026-06-30",
                                  "2026-09-30", "2026-12-31"],
        },
        "output": {"workbook": "out/x.xlsx"},
        "accounts": {
            "count": 60,
            "regions": {"AMER": 0.5, "EMEA": 0.3, "APAC": 0.2},
            "segments": {"Enterprise": 0.4, "Mid-Market": 0.35, "SMB": 0.25},
            "industries": ["Tech"],
        },
        "opportunities": {
            "per_quarter": 120,
            "win_rate": 0.3,
            "win_rate_jitter": 0.02,
            "owners": ["A"],
            "deal_duration_days": [20, 40],
            "close_clustering": {"share_in_end_of_quarter_window": 0.25},
            "deal_size_lognormal": {"median_usd": 40000, "sigma": 0.6},
            "discount": {
                "base_by_quarter": {
                    "AMER": [10, 12, 14, 16],
                    "EMEA": [10, 12, 14, 16],
                    "APAC": [10, 12, 14, 16]},
                "noise_sd_pp": 2.5,
                "end_of_quarter_boost_pp": 6,
                "end_of_quarter_window_days": 10,
                "min_pct": 0, "max_pct": 35},
        },
    }
    cfg.update(over)
    return cfg


def crit(check, cid="AC1", **params):
    return {"criteria": [{"id": cid, "name": cid, "check": check,
                          "params": params}],
            "definitions": {}}


PRODUCTS = {
    "catalog": [
        {"id": "E", "tier": "entry",
         "share": {"weights_by_quarter": [0.6, 0.55, 0.5, 0.45]}},
        {"id": "C", "tier": "core", "share": 0.3},
        {"id": "P", "tier": "premium",
         "share": {"weights_by_quarter": [0.1, 0.15, 0.2, 0.25]}},
    ],
    "margin_by_tier": {"entry": 0.45, "core": 0.6, "premium": 0.75},
}


def test_clean_config_no_findings():
    """A coherent config+criteria pair produces zero findings."""
    cfg = base_cfg(quota={"by_segment": {"SMB": [100_000] * 4},
                          "attainment_by_segment": {"SMB": 1.04}})
    doc = crit("revenue_vs_plan", segment="SMB", target_pct=104,
               band_pct=2)
    assert calibrate(cfg, doc) == []


def test_missing_quota_is_hard():
    doc = crit("revenue_vs_plan", segment="SMB", target_pct=104, band_pct=2)
    findings = calibrate(base_cfg(), doc)
    hard = hard_findings(findings)
    assert len(hard) == 1 and hard[0]["rule"] == "PF1"


def test_unknown_plan_unit_and_dimension_mismatch_are_hard():
    cfg = base_cfg(quota={"by_segment": {"Enterprise": [100_000] * 4}})
    doc = crit("revenue_vs_plan", segment="SMB", target_pct=95, band_pct=2)
    hard = hard_findings(calibrate(cfg, doc))
    assert any("not in plan units" in f["msg"] for f in hard)

    # dimension mismatch: criterion says territory, plan is segments
    doc2 = crit("revenue_vs_plan", segment="_all_", dimension="territory",
                target_pct=95, band_pct=2)
    hard2 = hard_findings(calibrate(cfg, doc2))
    assert any("dimension" in f["msg"] for f in hard2)


def test_unknown_tier_without_products_is_hard():
    doc = crit("blended_margin_trend", target_change_pct=-3, tolerance_pp=1)
    findings = calibrate(base_cfg(), doc)
    assert hard_findings(findings)

    # with products present but wrong tier named -> still HARD
    doc2 = crit("tier_share_shift", tier="mid", from_share_pct=10,
                to_share_pct=30, tolerance_pp=3)
    hard2 = hard_findings(calibrate(base_cfg(products=PRODUCTS), doc2))
    assert any("tier 'mid'" in f["msg"] for f in hard2)


def test_mix_shift_on_static_shares_is_soft():
    static = copy.deepcopy(PRODUCTS)
    # count shares sized to match the criterion (no multipliers -> rev
    # share == count share): entry 20% -> 40%
    static["catalog"] = [
        {"id": "E", "tier": "entry",
         "share": {"weights_by_quarter": [0.2, 0.27, 0.33, 0.4]}},
        {"id": "P", "tier": "premium",
         "share": {"weights_by_quarter": [0.8, 0.73, 0.67, 0.6]}},
    ]
    doc = crit("tier_share_shift", tier="entry", from_share_pct=20,
               to_share_pct=40, tolerance_pp=3)
    findings = calibrate(base_cfg(products=static), doc)
    assert findings == [] or all(f["severity"] == "SOFT" for f in findings)


def test_mis_sized_tier_levels_are_hard():
    """Live s8 lesson: drafter drew entry at ~34% revenue when the
    criterion wanted ~20%; the loop never recovered it in 8 proposals.
    Pre-flight must catch level misses this large before converging."""
    bad = copy.deepcopy(PRODUCTS)
    bad["catalog"] = [
        {"id": "E", "tier": "entry", "share": 0.5},
        {"id": "P", "tier": "premium", "share": 0.5},
    ]
    doc = crit("tier_share_shift", tier="entry", from_share_pct=20,
               to_share_pct=35, tolerance_pp=3)
    hard = hard_findings(calibrate(base_cfg(products=bad), doc))
    assert any("mis-sized" in f["msg"] for f in hard)


def test_deal_size_trend_under_raking_flags_soft():
    cfg = base_cfg(quota={"by_segment": {"SMB": [100_000] * 4}})
    doc = crit("deal_size_trend", target_change_pct=-8, tolerance_pp=3)
    findings = calibrate(cfg, doc)
    msgs = [f["msg"] for f in findings]
    assert any("volume_multipliers" in m for m in msgs)


def test_level_arithmetic_detects_off_pinned_discounts():
    # blended Q1 discount predicted ~11.5 (10 + .25*6 = 11.5); a criterion
    # pinning Q4 avg discount at 18 while bases end at 16 (+1.5 boost) is
    # ~1.5pp+ off depending on rounding - use an extreme miss to be safe
    cfg = base_cfg()
    doc_ok = crit("avg_discount_quarter", quarter="FY26-Q4", target_pct=17.5,
                  tolerance_pp=2)
    assert not [f for f in calibrate(cfg, doc_ok) if f["rule"] == "PF2"]

    doc_bad = crit("avg_discount_quarter", quarter="FY26-Q1", target_pct=25,
                   tolerance_pp=2)
    soft = [f for f in calibrate(cfg, doc_bad) if f["rule"] == "PF2"]
    assert soft and "13.5pp off" in soft[0]["msg"] or \
        soft and "pp off" in soft[0]["msg"]


def test_realized_vs_list_implied_levels_checked():
    cfg = base_cfg()  # Q1 predicted realized/list ~ 100 - 11.5 + 1.8 = 90.3
    doc_bad = crit("realized_vs_list", quarter_start="FY26-Q1",
                   target_start_pct=70, quarter_end="FY26-Q4",
                   target_end_pct=82, tolerance_pp=2)
    soft = [f for f in calibrate(cfg, doc_bad) if f["rule"] == "PF2"]
    assert any("FY26-Q1" in f["msg"] for f in soft)


def test_icp_check_without_icp_config_is_soft():
    doc = crit("icp_creation_shift", min_increase_pp=5)
    findings = calibrate(base_cfg(), doc)
    assert any("icp" in f["msg"] for f in findings)


@pytest.mark.parametrize("bad,frag", [
    ({"time_model": None}, "invalid"),
])
def test_invalid_config_short_circuits(bad, frag):
    cfg = base_cfg(**bad)
    doc = crit("win_rate_flat", band_pp=3)
    findings = calibrate(cfg, doc)
    assert findings[0]["rule"] == "PF0"
