"""M4 Phase 3: second story domain - sales-cycle slowdown.

Engine extensions (duration curves, volume multipliers) + the two new
checks (cycle_length_trend, creation_volume_trend), both directions.
"""
import json

import numpy as np
import pandas as pd
import pytest

from syngen.config import ConfigError, validate_simulator_doc
from syngen.generator.engine import generate, generate_to_workbook
from syngen.validator.checks import CHECKS
from syngen.validator.report import run_validation


def slowdown_cfg(**overrides):
    cfg = {
        "seed": 42,
        "time_model": {
            "fiscal_year": "FY26",
            "quarter_labels": ["FY26-Q1", "FY26-Q2", "FY26-Q3", "FY26-Q4"],
            "quarter_end_dates": ["2026-03-31", "2026-06-30",
                                  "2026-09-30", "2026-12-31"],
        },
        "output": {"workbook": "output/ds.xlsx"},
        "accounts": {
            "count": 40,
            "regions": {"AMER": 0.5, "EMEA": 0.5},
            "segments": {"Enterprise": 0.5, "SMB": 0.5},
            "industries": ["Software"],
        },
        "opportunities": {
            "per_quarter": 300,
            "win_rate": 0.3,
            "win_rate_jitter": 0.005,
            "owners": ["A Rep", "B Rep"],
            "deal_duration_days": {"means": [40, 50, 60, 70], "spread": 8},
            "volume_multipliers": [1.0, 0.93, 0.86, 0.80],
            "close_clustering": {"share_in_end_of_quarter_window": 0.25},
            "deal_size_lognormal": {"median_usd": 40000, "sigma": 0.7},
            "discount": {
                "base_by_quarter": {"AMER": [12, 12, 12, 12],
                                    "EMEA": [12, 12, 12, 12]},
                "noise_sd_pp": 2.5,
                "end_of_quarter_boost_pp": 6,
                "end_of_quarter_window_days": 10,
                "min_pct": 0,
                "max_pct": 40,
            },
        },
    }
    cfg.update(overrides)
    return validate_simulator_doc(cfg)


def test_duration_curve_shifts_cycle_time():
    opp = generate(slowdown_cfg())["opportunities"]
    won = opp[opp["stage"] == "Closed Won"].copy()
    won["cycle"] = (pd.to_datetime(won["close_date"])
                    - pd.to_datetime(won["created_date"])).dt.days
    q1 = won[won["fiscal_quarter"] == "FY26-Q1"]["cycle"].mean()
    q4 = won[won["fiscal_quarter"] == "FY26-Q4"]["cycle"].mean()
    assert q1 > 30 and q1 < 50, f"Q1 cycle {q1} should sit near 40"
    assert q4 > 60 and q4 < 80, f"Q4 cycle {q4} should sit near 70"


def test_duration_curve_grows_monotonically():
    opp = generate(slowdown_cfg())["opportunities"]
    won = opp[opp["stage"] == "Closed Won"].copy()
    won["cycle"] = (pd.to_datetime(won["close_date"])
                    - pd.to_datetime(won["created_date"])).dt.days
    means = [won[won["fiscal_quarter"] == q]["cycle"].mean()
             for q in ["FY26-Q1", "FY26-Q2", "FY26-Q3", "FY26-Q4"]]
    assert means == sorted(means), f"cycle avgs must rise: {means}"


def test_legacy_uniform_duration_still_works():
    cfg = slowdown_cfg()
    cfg["opportunities"]["deal_duration_days"] = [20, 40]
    del cfg["opportunities"]["volume_multipliers"]
    opp = generate(cfg)["opportunities"]
    cycles = ((pd.to_datetime(opp["close_date"])
               - pd.to_datetime(opp["created_date"])).dt.days)
    assert cycles.between(20, 39).mean() > 0.95


def test_volume_multipliers_respected_exactly():
    opp = generate(slowdown_cfg())["opportunities"]
    counts = opp.groupby("fiscal_quarter").size()
    expected = [round(300 * m) for m in (1.0, 0.93, 0.86, 0.80)]
    assert list(counts) == expected


def test_config_rejects_bad_duration_curve():
    cfg = slowdown_cfg()
    cfg["opportunities"]["deal_duration_days"] = {"means": [40, 50]}
    with pytest.raises(ConfigError, match="one value per quarter"):
        validate_simulator_doc(cfg)


def test_config_rejects_bad_multipliers():
    cfg = slowdown_cfg()
    cfg["opportunities"]["volume_multipliers"] = [1.0, -2, 1, 1]
    with pytest.raises(ConfigError, match="positive"):
        validate_simulator_doc(cfg)


# --- checks: both directions --------------------------------------------------

CRIT_CYCLE = {"definitions": {}, "criteria": [
    {"id": "AC20", "name": "cycles stretch", "check": "cycle_length_trend",
     "params": {"min_increase_pct": 50}}]}

CRIT_VOLUME = {"definitions": {}, "criteria": [
    {"id": "AC21", "name": "creation slows ~20%", "check": "creation_volume_trend",
     "params": {"target_decline_pct": 20, "tolerance_pp": 6}}]}


def _validate(tmp_path, cfg, criteria):
    cfg["output"]["workbook"] = str(tmp_path / "ds.xlsx")
    _, wb = generate_to_workbook(cfg)
    crit_path = tmp_path / "criteria.json"
    crit_path.write_text(json.dumps(criteria), encoding="utf-8")
    return run_validation(wb, crit_path)


def test_slowdown_story_lands(tmp_path):
    results, all_pass = _validate(tmp_path, slowdown_cfg(),
                                  {"definitions": {},
                                   "criteria": CRIT_CYCLE["criteria"]
                                   + CRIT_VOLUME["criteria"]})
    assert all_pass, [(r["id"], r["verdict"], r["detail"]) for r in results]


def test_flat_cycles_fail_growth_check(tmp_path):
    """Two-direction: constant durations must FAIL a +50% growth criterion."""
    cfg = slowdown_cfg()
    cfg["opportunities"]["deal_duration_days"] = {"means": [45, 45, 45, 45],
                                                  "spread": 8}
    results, all_pass = _validate(tmp_path, cfg, CRIT_CYCLE)
    assert not all_pass and results[0]["verdict"] == "FAIL"


def test_rising_volume_fails_decline_check(tmp_path):
    """Two-direction: growing creation must FAIL a decline-band criterion."""
    cfg = slowdown_cfg()
    cfg["opportunities"]["volume_multipliers"] = [1.0, 1.05, 1.1, 1.15]
    results, all_pass = _validate(tmp_path, cfg, CRIT_VOLUME)
    assert not all_pass and results[0]["verdict"] == "FAIL"


def test_check_direct_on_frames():
    """Direct unit: build frames with known cycle growth, check passes."""
    from datetime import timedelta
    opp = pd.DataFrame([
        {"fiscal_quarter": "FY26-Q1", "stage": "Closed Won",
         "close_date": pd.Timestamp("2026-03-01"),
         "created_date": pd.Timestamp("2026-03-01") - timedelta(days=40)},
        {"fiscal_quarter": "FY26-Q2", "stage": "Closed Won",
         "close_date": pd.Timestamp("2026-06-01"),
         "created_date": pd.Timestamp("2026-06-01") - timedelta(days=80)},
    ])
    accounts = pd.DataFrame({"account_id": ["A"], "segment": ["S"]})
    r = CHECKS["cycle_length_trend"](opp, accounts,
                                     {"min_increase_pct": 50,
                                      "quarter_ends": {
                                          "FY26-Q1": "x", "FY26-Q2": "y"}})
    assert r["ok"] and r["margin"] > 40  # 100% growth vs +50% needed
