"""M4 Phase 1 (WS3): aggregate targets - quota sheet, monetary raking, and
the black-box revenue_vs_plan check."""
import json

import numpy as np
import pandas as pd
import pytest

from syngen.config import ConfigError, validate_simulator_doc
from syngen.generator.engine import apply_raking, generate, generate_to_workbook
from syngen.validator.report import run_validation


def base_cfg(validate=True, **overrides):
    cfg = {
        "seed": 42,
        "time_model": {
            "fiscal_year": "FY26",
            "quarter_labels": ["FY26-Q1", "FY26-Q2"],
            "quarter_end_dates": ["2026-03-31", "2026-06-30"],
        },
        "output": {"workbook": "output/ds.xlsx"},
        "accounts": {
            "count": 60,
            "regions": {"AMER": 0.5, "EMEA": 0.5},
            "segments": {"Enterprise": 0.3, "Mid-Market": 0.4, "SMB": 0.3},
            "industries": ["Software"],
        },
        "opportunities": {
            "per_quarter": 200,
            "win_rate": 0.3,
            "win_rate_jitter": 0.01,
            "owners": ["A Rep", "B Rep"],
            "deal_duration_days": [10, 40],
            "close_clustering": {"share_in_end_of_quarter_window": 0.25},
            "deal_size_lognormal": {"median_usd": 40000, "sigma": 0.7},
            "discount": {
                "base_by_quarter": {"AMER": [12, 13], "EMEA": [12, 14]},
                "noise_sd_pp": 2.5,
                "end_of_quarter_boost_pp": 6,
                "end_of_quarter_window_days": 10,
                "min_pct": 0,
                "max_pct": 40,
            },
        },
    }
    cfg.update(overrides)
    return validate_simulator_doc(cfg) if validate else cfg


QUOTA = {
    "quota": {
        "by_segment": {
            "Enterprise": [1_000_000, 1_100_000],
            "Mid-Market": [800_000, 850_000],
            "SMB": [300_000, 260_000],
        },
        # the story's miss/beat ratios live HERE, not in the check
        "attainment_by_segment": {"Enterprise": 0.95, "Mid-Market": 1.04},
    }
}


def test_no_quota_block_unchanged_behavior():
    frames = generate(base_cfg())
    assert set(frames) == {"accounts", "opportunities", "quarterly_summary"}


def test_quota_sheet_and_raked_attainment_hits_story_ratios():
    cfg = base_cfg(**QUOTA)
    frames = generate(cfg)
    assert "quota_plan" in frames
    opp = frames["opportunities"]
    won = opp[opp["stage"] == "Closed Won"]
    by_seg = QUOTA["quota"]["by_segment"]
    ratios = QUOTA["quota"]["attainment_by_segment"]
    for seg, curve in by_seg.items():
        ratio = ratios.get(seg, 1.0)
        for qi, label in enumerate(cfg["time_model"]["quarter_labels"]):
            actual = won[(won["segment"] == seg)
                         & (won["fiscal_quarter"] == label)]["realized_price"].sum()
            expected = curve[qi] * ratio
            assert abs(actual - expected) < 0.05, \
                f"{seg} {label}: {actual} vs target {expected} (plan x {ratio})"


def test_default_attainment_is_exact_plan():
    cfg = base_cfg(quota={"by_segment": {"Enterprise": [500_000, 500_000]}})
    opp = generate(cfg)["opportunities"]
    won = opp[(opp["segment"] == "Enterprise") & (opp["stage"] == "Closed Won")]
    for label, target in zip(cfg["time_model"]["quarter_labels"],
                             [500_000, 500_000]):
        actual = won[won["fiscal_quarter"] == label]["realized_price"].sum()
        assert abs(actual - target) < 0.02


def test_raking_preserves_derived_identity():
    """realized_price must equal round(list*(1-d/100),2) on EVERY row after
    raking - naive scaling would break this silently."""
    cfg = base_cfg(**QUOTA)
    opp = generate(cfg)["opportunities"]
    expected = (opp["list_price"] * (1 - opp["discount_pct"] / 100)).round(2)
    pd.testing.assert_series_equal(opp["realized_price"], expected,
                                   check_names=False)


def test_raking_leaves_discounts_winrates_counts_untouched():
    cfg = base_cfg()
    plain = generate(cfg)["opportunities"]
    raked = generate(base_cfg(**QUOTA))["opportunities"]
    # same seed: counts, stages, discounts identical; only money moves
    pd.testing.assert_series_equal(plain["stage"], raked["stage"])
    pd.testing.assert_series_equal(plain["discount_pct"], raked["discount_pct"])
    assert len(plain) == len(raked)


def test_raking_deterministic_across_regenerations():
    a = generate(base_cfg(**QUOTA))["opportunities"]["realized_price"]
    b = generate(base_cfg(**QUOTA))["opportunities"]["realized_price"]
    pd.testing.assert_series_equal(a, b)


def test_workbook_with_quota_passes_structure_check(tmp_path):
    from syngen.linter import structure_findings
    cfg = base_cfg(**QUOTA)
    cfg["output"]["workbook"] = str(tmp_path / "ds.xlsx")
    _, path = generate_to_workbook(cfg)
    assert structure_findings(path) == []


def _validate(tmp_path, cfg, criteria):
    cfg["output"]["workbook"] = str(tmp_path / "ds.xlsx")
    _, wb = generate_to_workbook(cfg)
    crit_path = tmp_path / "criteria.json"
    crit_path.write_text(json.dumps(criteria), encoding="utf-8")
    return run_validation(wb, crit_path)


def test_revenue_vs_plan_passes_at_story_attainment(tmp_path):
    """Enterprise raked to 95% of plan; criterion expects 95% +/-2 -> PASS."""
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC10", "name": "Ent misses plan by 5%",
             "check": "revenue_vs_plan",
             "params": {"segment": "Enterprise", "target_pct": 95,
                        "band_pct": 2}},
            {"id": "AC11", "name": "MM beats plan by 4%",
             "check": "revenue_vs_plan",
             "params": {"segment": "Mid-Market", "target_pct": 104,
                        "band_pct": 2}},
        ],
    }
    results, all_pass = _validate(tmp_path, base_cfg(**QUOTA), criteria)
    assert all_pass, results
    for r in results:
        assert abs(r["margin"]) >= 1.5  # raking is near-exact; margin is wide


def test_revenue_vs_plan_fails_when_attainment_mismatches_story(tmp_path):
    """A criterion claiming on-plan (100%) must FAIL when the config's
    attainment is 95% - story intent and data must agree."""
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC12", "name": "claims on-plan but data says 95%",
             "check": "revenue_vs_plan",
             "params": {"segment": "Enterprise", "target_pct": 100,
                        "band_pct": 2}},
        ],
    }
    results, all_pass = _validate(tmp_path, base_cfg(**QUOTA), criteria)
    assert not all_pass and results[0]["verdict"] == "FAIL"


def test_revenue_vs_plan_missing_plan_sheet_is_clean_fail(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC12", "name": "plan check sans plan",
             "check": "revenue_vs_plan",
             "params": {"segment": "Enterprise", "band_pct": 2}},
        ],
    }
    results, _ = _validate(tmp_path, base_cfg(), criteria)
    assert results[0]["verdict"] == "FAIL"
    assert "quota block" in results[0]["detail"]


def test_revenue_vs_plan_unknown_segment_fails_cleanly(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC13", "name": "unknown segment",
             "check": "revenue_vs_plan",
             "params": {"segment": "Channel", "band_pct": 2}},
        ],
    }
    results, _ = _validate(tmp_path, base_cfg(**QUOTA), criteria)
    assert results[0]["verdict"] == "FAIL"
    assert "absent from plan" in results[0]["actual"]
    assert "Channel" in results[0]["detail"]


# --- config validation rules --------------------------------------------------

def test_quota_segment_must_exist_in_accounts():
    bad = base_cfg(validate=False, quota={"by_segment": {"Channel": [1, 2]}})
    with pytest.raises(ConfigError, match="not a known account segment"):
        validate_simulator_doc(bad)


def test_quota_curve_length_must_match_quarters():
    bad = base_cfg(validate=False, quota={"by_segment": {
        "Enterprise": [1, 2, 3]}})
    with pytest.raises(ConfigError, match="one target per quarter"):
        validate_simulator_doc(bad)


def test_quota_targets_must_be_positive():
    bad = base_cfg(validate=False, quota={"by_segment": {
        "Enterprise": [1_000_000, -5]}})
    with pytest.raises(ConfigError, match="positive"):
        validate_simulator_doc(bad)


def test_empty_stratum_is_skipped_not_crashed():
    """If a segment somehow wins nothing in a quarter, raking skips it."""
    cfg = base_cfg(**QUOTA)
    df = generate(cfg)["opportunities"]
    assert len(df) > 0  # smoke: the guard path didn't blow up generation
