"""M5 iter 4 (WS1 rest): Rep entity, capacity/ramp model, and the
black-box effective_capacity check."""
import json

import pandas as pd
import pytest

from syngen.config import ConfigError, validate_simulator_doc
from syngen.generator.engine import generate, generate_to_workbook
from syngen.linter import structure_findings
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
            "territories": {"East": ["AMER"], "West": ["EMEA"]},
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


CAPACITY = {
    "capacity": {
        "by_territory": {
            "East": {"headcount_plan": [10, 10],
                     "headcount_actual": [9, 10],
                     "ramping_reps_by_quarter": [1, 2],
                     "ramp_productivity_pct": 50},
            "West": {"headcount_plan": [8, 8]},
        }
    }
}


def test_no_capacity_block_unchanged_behavior():
    frames = generate(base_cfg())
    assert set(frames) == {"accounts", "opportunities",
                           "quarterly_summary"}


def test_capacity_block_emits_reps_and_plan_sheets():
    frames = generate(base_cfg(**CAPACITY))
    assert set(frames) >= {"reps", "capacity_plan"}
    assert list(frames["reps"].columns) == [
        "rep_id", "rep_name", "territory", "hire_fiscal_quarter"]
    assert list(frames["capacity_plan"].columns) == [
        "fiscal_quarter", "plan_unit_type", "plan_unit", "headcount_plan",
        "headcount_actual", "ramping_reps", "ramp_productivity_pct",
        "effective_capacity_pct"]
    assert set(frames["capacity_plan"]["plan_unit_type"]) == {"territory"}


def test_effective_capacity_math_is_exact():
    cap = generate(base_cfg(**CAPACITY))["capacity_plan"]
    east = cap[cap["plan_unit"] == "East"].set_index("fiscal_quarter")
    # Q1: ((9-1)+1*0.5)/10 = 85%   Q2: ((10-2)+2*0.5)/10 = 90%
    assert east.loc["FY26-Q1", "effective_capacity_pct"] == 85.0
    assert east.loc["FY26-Q2", "effective_capacity_pct"] == 90.0
    west = cap[cap["plan_unit"] == "West"].set_index("fiscal_quarter")
    assert (west["effective_capacity_pct"] == 100.0).all()


def test_default_actual_equals_plan_and_zero_ramping():
    cfg = base_cfg(capacity={"by_territory": {
        "East": {"headcount_plan": [4, 4]}}})
    cap = generate(cfg)["capacity_plan"]
    assert (cap["headcount_actual"] == 4).all()
    assert (cap["ramping_reps"] == 0).all()
    assert (cap["ramp_productivity_pct"] == 100.0).all()
    assert (cap["effective_capacity_pct"] == 100.0).all()


def test_rep_roster_derives_hires_between_quarters():
    reps = generate(base_cfg(**CAPACITY))["reps"]
    east = reps[reps["territory"] == "East"]
    tenured = east[east["hire_fiscal_quarter"].isna()]
    hired_q2 = east[east["hire_fiscal_quarter"] == "FY26-Q2"]
    assert len(tenured) == 9          # Q1 actual headcount
    assert len(hired_q2) == 1         # 9 -> 10 between quarters
    assert len(east) == 10
    assert east["rep_id"].is_unique
    assert reps["rep_id"].is_unique   # ids unique across territories too


def test_roster_names_deterministic():
    a = generate(base_cfg(**CAPACITY))["reps"]
    b = generate(base_cfg(**CAPACITY))["reps"]
    pd.testing.assert_frame_equal(a, b)


def test_capacity_by_region_dimension():
    cfg = base_cfg(validate=False)
    del cfg["accounts"]["territories"]
    cfg["accounts"]["regions"] = {"AMER": 0.5, "EMEA": 0.5}
    cfg["capacity"] = {"by_region": {"AMER": {"headcount_plan": [6, 6]}}}
    frames = generate(validate_simulator_doc(cfg))
    cap = frames["capacity_plan"]
    assert set(cap["plan_unit_type"]) == {"region"}
    assert list(frames["reps"].columns) == [
        "rep_id", "rep_name", "region", "hire_fiscal_quarter"]


# --- config validation rules ---------------------------------------------------

def test_capacity_needs_exactly_one_dimension():
    bad = base_cfg(validate=False)
    bad["capacity"] = {}
    with pytest.raises(ConfigError, match="exactly one of by_territory"):
        validate_simulator_doc(bad)
    bad["capacity"] = {"by_territory": {"East": {"headcount_plan": [1, 1]}},
                       "by_region": {"AMER": {"headcount_plan": [1, 1]}}}
    with pytest.raises(ConfigError, match="exactly one of by_territory"):
        validate_simulator_doc(bad)


def test_capacity_unknown_territory_rejected():
    bad = base_cfg(validate=False, capacity={"by_territory": {
        "Atlantis": {"headcount_plan": [1, 1]}}})
    with pytest.raises(ConfigError, match="not a known account territory"):
        validate_simulator_doc(bad)


def test_capacity_headcount_curve_length_must_match_quarters():
    bad = base_cfg(validate=False, capacity={"by_territory": {
        "East": {"headcount_plan": [1]}}})
    with pytest.raises(ConfigError, match="one value per quarter"):
        validate_simulator_doc(bad)


def test_capacity_headcounts_must_be_positive_ints():
    bad = base_cfg(validate=False, capacity={"by_territory": {
        "East": {"headcount_plan": [0, 4]}}})
    with pytest.raises(ConfigError, match="positive integers"):
        validate_simulator_doc(bad)
    bad = base_cfg(validate=False, capacity={"by_territory": {
        "East": {"headcount_plan": [3.5, 4]}}})
    with pytest.raises(ConfigError, match="positive integers"):
        validate_simulator_doc(bad)


def test_capacity_ramping_may_not_exceed_actual_headcount():
    bad = base_cfg(validate=False, capacity={"by_territory": {
        "East": {"headcount_plan": [5, 5],
                 "headcount_actual": [5, 5],
                 "ramping_reps_by_quarter": [2, 7]}}})
    with pytest.raises(ConfigError, match="exceeds actual headcount"):
        validate_simulator_doc(bad)


def test_capacity_ramp_productivity_bounds():
    bad = base_cfg(validate=False, capacity={"by_territory": {
        "East": {"headcount_plan": [5, 5], "ramp_productivity_pct": 120}}})
    with pytest.raises(ConfigError, match=r"\(0, 100\]"):
        validate_simulator_doc(bad)


# --- structural contract + black-box check --------------------------------------

def _validate(tmp_path, cfg, criteria):
    cfg["output"]["workbook"] = str(tmp_path / "ds.xlsx")
    _, wb = generate_to_workbook(cfg)
    assert structure_findings(wb, cfg) == []
    crit_path = tmp_path / "criteria.json"
    crit_path.write_text(json.dumps(criteria), encoding="utf-8")
    return run_validation(wb, crit_path)


def test_workbook_with_capacity_passes_structure_check(tmp_path):
    results, all_pass = _validate(
        tmp_path, base_cfg(**CAPACITY),
        {"definitions": {}, "criteria": []})
    assert all_pass


def test_effective_capacity_check_passes_in_band(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "effective capacity 85-90%",
             "check": "effective_capacity",
             "params": {"unit": "East", "target_pct": 87.5,
                        "band_pp": 2.5}},
        ],
    }
    results, all_pass = _validate(tmp_path, base_cfg(**CAPACITY), criteria)
    assert all_pass, results
    # worst row (Q1 85%) deviates exactly the 2.5pp band -> zero margin
    assert results[0]["margin"] == 0.0


def test_effective_capacity_check_fails_outside_band(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "claims fully productive capacity",
             "check": "effective_capacity",
             "params": {"unit": "East", "target_pct": 100,
                        "band_pp": 2.0}},
        ],
    }
    results, all_pass = _validate(tmp_path, base_cfg(**CAPACITY), criteria)
    assert not all_pass and results[0]["verdict"] == "FAIL"
    assert results[0]["margin"] < -10  # 85% vs 100% target is far off


def test_effective_capacity_all_units_when_no_unit_given(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "company-wide effective capacity",
             "check": "effective_capacity",
             "params": {"target_pct": 95, "band_pp": 6.0}},
        ],
    }
    results, all_pass = _validate(tmp_path, base_cfg(**CAPACITY), criteria)
    # West sits at 100%, worst row (East 85%) decides -> FAIL at band 6
    assert not all_pass and "East" in results[0]["actual"]


def test_effective_capacity_without_block_is_structural_fail(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "capacity claim sans capacity block",
             "check": "effective_capacity",
             "params": {"target_pct": 90, "band_pp": 2.0}},
        ],
    }
    results, _ = _validate(tmp_path, base_cfg(), criteria)
    assert results[0]["verdict"] == "FAIL"
    assert "capacity block" in results[0]["detail"]


def test_effective_capacity_unknown_unit_fails_cleanly(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "unknown unit",
             "check": "effective_capacity",
             "params": {"unit": "North", "band_pp": 2.0}},
        ],
    }
    results, _ = _validate(tmp_path, base_cfg(**CAPACITY), criteria)
    assert results[0]["verdict"] == "FAIL"
    assert "North" in results[0]["actual"]


# --- F28: per-territory potential overrides --------------------------------------

def test_potential_overrides_concentrate_whitespace():
    """Territories with overrides carry different potential without
    touching the sampling streams."""
    from syngen.validator.checks import CHECKS
    cfg = base_cfg(validate=False)
    cfg["accounts"]["market_potential_usd"] = {
        "min": 10_000, "max": 100_000,
        "by_territory": {"East": {"min": 800_000, "max": 900_000},
                         "West": {"min": 5_000, "max": 15_000}}}
    frames = generate(validate_simulator_doc(cfg))
    acc = frames["accounts"]
    means = acc.groupby("territory")["market_potential_usd"].mean()
    assert means["East"] > 700_000 and means["West"] < 20_000
    # streams untouched: opportunities identical to the no-override run
    plain = generate(base_cfg())["opportunities"]
    pd.testing.assert_frame_equal(
        plain, frames["opportunities"])


def test_potential_override_validation_rejects_unknown_territory():
    bad = base_cfg(validate=False)
    bad["accounts"]["market_potential_usd"] = {
        "min": 1_000, "max": 100_000,
        "by_territory": {"Atlantis": {"min": 1, "max": 2}}}
    with pytest.raises(ConfigError, match="not a known unit"):
        validate_simulator_doc(bad)


def test_engine_sampling_streams_untouched_by_capacity_block():
    """Capacity adds sheets only - opportunities must reproduce exactly."""
    plain = generate(base_cfg())["opportunities"]
    capped = generate(base_cfg(**CAPACITY))["opportunities"]
    pd.testing.assert_frame_equal(plain, capped)


# --- #15: quota vs addressable market -------------------------------------------

POTENTIAL_QUOTA = {
    "accounts": {
        "count": 60,
        "regions": {"AMER": 0.5, "EMEA": 0.5},
        "segments": {"Enterprise": 0.3, "Mid-Market": 0.4, "SMB": 0.3},
        "industries": ["Software"],
        "territories": {"Big": ["AMER"], "Small": ["EMEA"]},
        "market_potential_usd": {"min": 400_000, "max": 600_000},
    },
    "quota": {
        "by_territory": {"Big": [1_000_000, 1_000_000],
                         "Small": [200_000, 200_000]},
    },
}


def test_quota_vs_potential_flags_over_market_quota(tmp_path):
    """~30 accounts x ~$500k potential = ~$15M per territory side; Big's
    $2M quota is far BELOW potential, so a 'quotas above market' claim
    must FAIL for Big and PASS for Small (tiny quota)."""
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "Big quota far above addressable market",
             "check": "quota_vs_potential",
             "params": {"unit": "Big", "dimension": "territory",
                        "target_ratio_pct": 120, "band_pp": 10}},
            {"id": "AC2", "name": "Small quota tiny vs market",
             "check": "quota_vs_potential",
             "params": {"unit": "Small", "dimension": "territory",
                        "target_ratio_pct": 3, "band_pp": 2}},
        ],
    }
    results, _ = _validate(tmp_path, base_cfg(**POTENTIAL_QUOTA), criteria)
    assert results[0]["verdict"] == "FAIL"   # ratio ~13%, not 120%
    assert results[1]["verdict"] == "PASS"


def test_quota_vs_potential_without_plan_is_structural(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "quota ratio sans plan",
             "check": "quota_vs_potential",
             "params": {"dimension": "territory", "target_ratio_pct": 120,
                        "band_pp": 10}},
        ],
    }
    results, _ = _validate(tmp_path, base_cfg(), criteria)
    assert results[0]["verdict"] == "FAIL"
    assert "quota block" in results[0]["detail"]


# --- #4: whitespace under-coverage ------------------------------------------------

def test_potential_coverage_gap_detects_misplaced_pipeline():
    """Hand-built frames, both directions: even creation across an
    unbalanced potential map = under-covered whitespace; potential-aligned
    creation = no gap."""
    from syngen.validator.checks import CHECKS
    acc = pd.DataFrame({
        "territory": ["East"] * 30 + ["West"] * 30,
        "market_potential_usd": [1_000_000.0] * 30 + [10_000.0] * 30,
    })
    params = {"dimension": "territory", "min_gap_pp": 25.0}

    def opp_for(east_n, west_n):
        rows = [{"territory": t} for t in ["East"] * east_n +
                ["West"] * west_n]
        return pd.DataFrame(rows)

    # East holds ~99% of potential but only half the created pipeline
    r_under = CHECKS["potential_coverage_gap"](
        opp_for(50, 50), acc, params)
    assert r_under["ok"], r_under["detail"]
    # creation follows potential: East takes ~all pipeline -> no gap
    r_aligned = CHECKS["potential_coverage_gap"](
        opp_for(95, 5), acc, params)
    assert not r_aligned["ok"]
    assert r_aligned["margin"] < 0


def test_potential_coverage_gap_needs_territories_or_regions(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "whitespace claim",
             "check": "potential_coverage_gap",
             "params": {"dimension": "territory", "min_gap_pp": 5}},
        ],
    }
    cfg = base_cfg()
    del cfg["accounts"]["territories"]
    results, _ = _validate(tmp_path, cfg, criteria)
    assert results[0]["verdict"] == "FAIL"
    assert "lacks territories" in results[0]["detail"]


# --- #10: headcount growth placement -----------------------------------------------

def growth_cfg(strong_actual, weak_actual):
    """Two-territory rig: Strong is raked to ~10x Weak's revenue, so it is
    deterministically the 'historically strong' half."""
    cfg = base_cfg(validate=False)
    cfg["accounts"]["territories"] = {"Strong": ["AMER"], "Weak": ["EMEA"]}
    cfg["capacity"] = {"by_territory": {
        "Strong": {"headcount_plan": strong_actual,
                   "headcount_actual": strong_actual},
        "Weak": {"headcount_plan": weak_actual,
                 "headcount_actual": weak_actual},
    }}
    cfg["quota"] = {"by_territory": {"Strong": [500_000, 500_000],
                                     "Weak": [50_000, 50_000]}}
    return validate_simulator_doc(cfg)


def test_headcount_growth_to_strong_units_passes(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "additions went to strong territories",
             "check": "headcount_growth_placement",
             "params": {"min_growth_share_pct": 80}},
        ],
    }
    results, all_pass = _validate(
        tmp_path, growth_cfg([10, 14], [10, 10]), criteria)
    assert all_pass, results


def test_headcount_growth_to_weak_units_fails(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "story claims strong-side placement",
             "check": "headcount_growth_placement",
             "params": {"min_growth_share_pct": 80}},
        ],
    }
    results, _ = _validate(
        tmp_path, growth_cfg([10, 10], [10, 16]), criteria)
    assert results[0]["verdict"] == "FAIL"


def test_headcount_placement_without_capacity_is_structural(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "placement sans capacity",
             "check": "headcount_growth_placement",
             "params": {"min_growth_share_pct": 50}},
        ],
    }
    results, _ = _validate(tmp_path, base_cfg(), criteria)
    assert results[0]["verdict"] == "FAIL"
    assert "capacity block" in results[0]["detail"]


# --- D1 (WS7): ownership history --------------------------------------------------

OWNERSHIP = {
    "ownership": {
        "unowned_share_by_quarter": [0.0, 0.3],
        "churn_share_by_quarter": [0.0, 0.2],
        "owner_pool": ["Rep One", "Rep Two", "Rep Three"],
    }
}


def test_ownership_block_emits_history_sheet():
    frames = generate(base_cfg(**OWNERSHIP))
    assert "account_ownership" in frames
    own = frames["account_ownership"]
    assert list(own.columns) == ["account_id", "fiscal_quarter", "owner"]
    assert len(own) == 120  # 60 accounts x 2 quarters
    q1 = own[own["fiscal_quarter"] == "FY26-Q1"]
    q2 = own[own["fiscal_quarter"] == "FY26-Q2"]
    assert q1["owner"].notna().all()           # Q1 fully owned
    assert q2["owner"].isna().mean() == pytest.approx(0.3, abs=0.02)
    assert set(q2["owner"].dropna().unique()) <= set(OWNERSHIP[
        "ownership"]["owner_pool"])


def test_ownership_deterministic_and_churn_moves_owners():
    a = generate(base_cfg(**OWNERSHIP))["account_ownership"]
    b = generate(base_cfg(**OWNERSHIP))["account_ownership"]
    pd.testing.assert_frame_equal(a, b)
    q1 = a[a["fiscal_quarter"] == "FY26-Q1"].set_index("account_id")["owner"]
    q2 = a[a["fiscal_quarter"] == "FY26-Q2"].set_index("account_id")["owner"]
    both_owned = q1.notna() & q2.notna()
    changed = (q1[both_owned] != q2[both_owned]).sum()
    assert changed > 0  # churn actually reassigns


def test_no_ownership_block_no_sheet():
    assert "account_ownership" not in generate(base_cfg())


def test_win_rate_multiplier_couples_to_recent_changes():
    """A punishing post-change multiplier must lower the win rate on
    changed-owner accounts vs stable ones."""
    cfg = base_cfg(validate=False, **{
        "accounts": dict(base_cfg(validate=False)["accounts"])})
    cfg["opportunities"]["per_quarter"] = 2000
    cfg["ownership"] = {
        "churn_share_by_quarter": [0.0, 1.0],  # EVERYONE changes in Q2
        "win_rate_multiplier_after_change": 0.4,
    }
    cfg = validate_simulator_doc(cfg)
    opp = generate(cfg)["opportunities"]

    def wr(q):
        d = opp[(opp["fiscal_quarter"] == q)
                & opp["stage"].isin(["Closed Won", "Closed Lost"])]
        return (d["stage"] == "Closed Won").mean()

    # Q2 win rate should crater far below Q1's ~30%
    assert wr("FY26-Q2") < 0.18
    assert wr("FY26-Q1") > 0.25


def test_unowned_account_share_check_end_to_end(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "strategic accounts left unowned",
             "check": "unowned_account_share",
             "params": {"top_value_pct": 20,
                        "min_unowned_share_pct": 20}},
        ],
    }
    results, _ = _validate(tmp_path, base_cfg(**OWNERSHIP), criteria)
    assert results[0]["verdict"] == "PASS"
    # and the inverse claim fails: no unowned accounts anywhere
    cfg_plain = base_cfg(ownership={"unowned_share_by_quarter": [0.0, 0.0]})
    results, _ = _validate(tmp_path, cfg_plain, criteria)
    assert results[0]["verdict"] == "FAIL"


def test_unowned_check_without_block_is_structural(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "unowned claim sans ownership block",
             "check": "unowned_account_share",
             "params": {"min_unowned_share_pct": 10}},
        ],
    }
    results, _ = _validate(tmp_path, base_cfg(), criteria)
    assert results[0]["verdict"] == "FAIL"
    assert "ownership block" in results[0]["detail"]


def test_post_change_revenue_decline_detects_churn_drag(tmp_path):
    cfg = base_cfg(validate=False)
    cfg["opportunities"]["per_quarter"] = 2000
    cfg["ownership"] = {
        "churn_share_by_quarter": [0.0, 1.0],
        "win_rate_multiplier_after_change": 0.35,
    }
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "revenue fell where owners changed",
             "check": "post_change_revenue_decline",
             "params": {"min_gap_pp": 30}},
        ],
    }
    results, all_pass = _validate(
        tmp_path, validate_simulator_doc(cfg), criteria)
    assert all_pass, results


# --- D2 (WS7): activity fact table --------------------------------------------------

ACTIVITY = {
    "activity": {
        "mean_touches_per_account_by_quarter": [3.0, 3.0],
        "potential_tilt": -2.5,
    },
    "forecast": {
        "commit_ratio_by_quarter": [1.09, 1.09],
        "commit_share_of_won_by_quarter": [0.4, 0.4],
        "low_activity_bias": 2.0,
    },
}


def test_activity_block_emits_fact_table():
    frames = generate(base_cfg(**ACTIVITY))
    assert "account_activity" in frames
    act = frames["account_activity"]
    assert list(act.columns) == ["account_id", "fiscal_quarter", "touches"]
    assert len(act) == 120
    a = generate(base_cfg(**ACTIVITY))["account_activity"]
    pd.testing.assert_frame_equal(act, a)  # deterministic


def test_negative_tilt_points_activity_at_low_potential():
    from syngen.validator.checks import CHECKS
    cfg = base_cfg(validate=False)
    cfg["accounts"]["market_potential_usd"] = {"min": 10_000, "max": 900_000}
    frames = generate(validate_simulator_doc(cfg))

    def bottom_share(tilt):
        cfg2 = dict(frames and validate_simulator_doc(dict(
            cfg, activity={"mean_touches_per_account_by_quarter": [5.0, 5.0],
                           "potential_tilt": tilt})))
        act = generate(cfg2)["account_activity"]
        acc = generate(cfg2)["accounts"].set_index("account_id")
        merged = act.copy()
        merged["pot"] = merged["account_id"].map(acc["market_potential_usd"])
        total_t = merged["touches"].sum()
        lo_pot = merged[merged["pot"] <= merged["pot"].median()]
        return lo_pot["touches"].sum() / total_t * 100

    # negative tilt: low-potential half gets MORE than its fair share (>50%)
    assert bottom_share(-2.5) > 55
    # positive tilt: less than half
    assert bottom_share(2.5) < 45


def test_activity_misalignment_check_two_directions():
    from syngen.validator.checks import CHECKS
    cfg = validate_simulator_doc(base_cfg(validate=False, **{
        "activity": {"mean_touches_per_account_by_quarter": [5.0, 5.0],
                     "potential_tilt": -2.5}}))
    frames = generate(cfg)
    r = CHECKS["activity_potential_misalignment"](
        frames["opportunities"], frames["accounts"],
        {"_activity_df": frames["account_activity"], "min_gap_pp": 15.0})
    assert r["ok"], r["detail"]
    flat = validate_simulator_doc(base_cfg(validate=False, **{
        "activity": {"mean_touches_per_account_by_quarter": [5.0, 5.0]}}))
    f2 = generate(flat)
    r2 = CHECKS["activity_potential_misalignment"](
        f2["opportunities"], f2["accounts"],
        {"_activity_df": f2["account_activity"], "min_gap_pp": 15.0})
    assert not r2["ok"]


def test_forecast_snapshot_and_commit_flags():
    frames = generate(base_cfg(**ACTIVITY))
    fc = frames["forecast_snapshot"]
    assert list(fc.columns) == ["fiscal_quarter", "committed_usd",
                                "actual_usd", "commit_vs_actual_pct"]
    assert (fc["commit_vs_actual_pct"] == 109.0).all()
    opp = frames["opportunities"]
    assert "in_commit" in opp.columns
    won = opp[opp["stage"] == "Closed Won"]
    assert won["in_commit"].mean() == pytest.approx(0.4, abs=0.05)


def test_commit_concentrated_on_zero_touch_accounts(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "commit sits on no-engagement deals",
             "check": "commit_no_engagement_share",
             "params": {"min_share_pct": 20}},
        ],
    }
    results, _ = _validate(tmp_path, base_cfg(**ACTIVITY), criteria)
    assert results[0]["verdict"] == "PASS"


def test_commit_check_structural_without_blocks(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "commit claim sans blocks",
             "check": "commit_no_engagement_share",
             "params": {"min_share_pct": 10}},
        ],
    }
    results, _ = _validate(tmp_path, base_cfg(), criteria)
    assert results[0]["verdict"] == "FAIL"
    assert "forecast block" in results[0]["detail"]


def test_forecast_vs_actual_check_end_to_end(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "forecast +9%",
             "check": "forecast_vs_actual",
             "params": {"target_pct": 109, "band_pp": 1}},
        ],
    }
    results, all_pass = _validate(tmp_path, base_cfg(**ACTIVITY), criteria)
    assert all_pass, results
    bad = base_cfg(forecast={"commit_ratio_by_quarter": [1.02, 0.97]})
    results, _ = _validate(tmp_path, bad, criteria)
    assert results[0]["verdict"] == "FAIL"


# --- D4 (WS7): motion dimension (#22) -----------------------------------------------

MOTION_QUOTA = {
    "quota": {
        "by_motion": {"Expansion": [400_000, 400_000],
                      "New Logo": [100_000, 100_000]},
        "attainment": {"Expansion": 1.06, "New Logo": 0.97},
    }
}


def test_motion_dimension_rakes_attainment_exact(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "expansion beat plan by 6%",
             "check": "revenue_vs_plan",
             "params": {"segment": "Expansion", "dimension": "motion",
                        "target_pct": 106, "band_pct": 1}},
            {"id": "AC2", "name": "new logo missed by 3%",
             "check": "revenue_vs_plan",
             "params": {"segment": "New Logo", "dimension": "motion",
                        "target_pct": 97, "band_pct": 1}},
        ],
    }
    results, all_pass = _validate(
        tmp_path, base_cfg(**MOTION_QUOTA), criteria)
    assert all_pass, results


def test_motion_classification_first_deal_is_new_logo():
    frames = generate(base_cfg(**MOTION_QUOTA))
    opp = frames["opportunities"]
    assert set(opp["motion"].unique()) <= {"New Logo", "Expansion"}
    firsts = opp.drop_duplicates("account_id", keep="first")
    assert (firsts["motion"] == "New Logo").all()


def test_motion_gap_concentration_works(tmp_path):
    """gap_concentration with dimension motion - the generic plan-unit
    analysis must work over the motion stratum too."""
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "gap concentrated in new logo",
             "check": "gap_concentration",
             "params": {"dimension": "motion",
                        "min_bottom_gap_share_pct": 90}},
        ],
    }
    results, _ = _validate(tmp_path, base_cfg(**MOTION_QUOTA), criteria)
    # New Logo misses by 3%, Expansion beats by 6% -> New Logo IS the gap
    assert results[0]["verdict"] == "PASS"


def test_engine_streams_untouched_by_ws7_sheets():
    """Ownership/activity/forecast/capacity blocks never shift the core
    sampling streams - opportunities identical without them."""
    plain = generate(base_cfg())["opportunities"]
    full = base_cfg(validate=False)
    full.update({
        "capacity": {"by_territory": {"East": {"headcount_plan": [5, 5]}}},
        "ownership": {"unowned_share_by_quarter": [0.1, 0.1]},
        "activity": {"mean_touches_per_account_by_quarter": [2.0, 2.0]},
        "forecast": {"commit_ratio_by_quarter": [1.05, 1.05]},
    })
    rich = generate(validate_simulator_doc(full))["opportunities"]
    shared = [c for c in plain.columns if c in rich.columns]
    pd.testing.assert_frame_equal(plain[shared], rich[shared])


# --- E1 (WS8): mixture-aware raking (#25) ------------------------------------------

WHALE_QUOTA = {
    "opportunities": dict(
        base_cfg(validate=False)["opportunities"],
        outlier_deals={"share": 0.05, "multiplier": 20}),
    "quota": {
        "by_segment": {
            "Enterprise": [400_000, 400_000],
            "Mid-Market": [300_000, 300_000],
            "SMB": [200_000, 200_000],
        },
        "attainment_by_segment": {"Enterprise": 1.01},
        # headline 101% but the CORE business actually missed at ~90%
        "attainment_ex_outliers": {"Enterprise": 0.90},
    },
}


def test_outlier_flag_persists_and_matches_whale_share():
    frames = generate(base_cfg(**WHALE_QUOTA))
    opp = frames["opportunities"]
    assert "is_outlier" in opp.columns
    share = opp[opp["fiscal_quarter"] == "FY26-Q1"]["is_outlier"].mean()
    assert share == pytest.approx(0.05, abs=0.01)
    assert not opp.loc[~opp["is_outlier"], "is_outlier"].any()


def test_mixture_raking_hits_headline_and_core(tmp_path):
    """The #25 shape: _all_ attainment ~101% while ex-whale attainment
    lands at ~90% - both from the same dataset."""
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "headline beat via whales",
             "check": "revenue_vs_plan",
             "params": {"segment": "Enterprise", "dimension": "segment",
                        "target_pct": 101, "band_pct": 0.05}},
            {"id": "AC2", "name": "core business missed",
             "check": "revenue_vs_plan",
             "params": {"segment": "Enterprise", "dimension": "segment",
                        "target_pct": 90, "band_pct": 0.05,
                        "exclude_outlier_deals": True}},
        ],
    }
    results, all_pass = _validate(tmp_path, base_cfg(**WHALE_QUOTA), criteria)
    assert all_pass, results


def test_mixture_raking_without_outliers_is_structural(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "ex-whale claim sans outliers",
             "check": "revenue_vs_plan",
             "params": {"segment": "_all_", "target_pct": 90,
                        "band_pct": 1, "exclude_outlier_deals": True}},
        ],
    }
    plain_quota = {"quota": WHALE_QUOTA["quota"]}
    del plain_quota["quota"]["attainment_ex_outliers"]
    results, _ = _validate(tmp_path, base_cfg(**plain_quota), criteria)
    assert results[0]["verdict"] == "FAIL"
    assert "outlier_deals" in results[0]["detail"]


# --- E2 (#16) + E3 (#17) ------------------------------------------------------------

def _elastic_cfg():
    cfg = base_cfg(validate=False)
    cfg["accounts"] = dict(cfg["accounts"],
                           market_potential_usd={"min": 10_000,
                                                 "max": 900_000})
    cfg["opportunities"] = dict(cfg["opportunities"], per_quarter=1500)
    cfg["pricing_response"] = {
        "price_change_pct_by_quarter": [0, 8],
        "elasticity": -3.0,
        "potential_mitigation": 0.9,
    }
    return cfg


def test_elasticity_hurts_low_potential_more():
    from syngen.validator.checks import CHECKS
    frames = generate(validate_simulator_doc(_elastic_cfg()))
    r = CHECKS["elasticity_differential"](
        frames["opportunities"], frames["accounts"], {"min_gap_pp": 0.0})
    assert r["ok"], r["detail"]
    # and materially large: low-potential conversion visibly trails
    assert r["margin"] > 3.0


def test_elasticity_check_requires_potential(tmp_path):
    """Without a pricing_response block there is no differential to find:
    the check runs (potential always exists on accounts) and fails."""
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "elasticity sans pricing response",
             "check": "elasticity_differential",
             "params": {"min_gap_pp": 25}},
        ],
    }
    results, _ = _validate(tmp_path, base_cfg(), criteria)
    assert results[0]["verdict"] == "FAIL"


def test_core_vs_headline_detects_whale_masking():
    """Hand-built frames: whales grow while core shrinks -> headline up,
    core down. (Raking pins both quarters to plan, so this pathology is
    expressed via attainment_ex_outliers in real configs; the check's
    arithmetic is what's under test here.)"""
    from syngen.validator.checks import CHECKS
    rows = []
    for qi, q in enumerate(["FY26-Q1", "FY26-Q2"]):
        n_core = 9 if qi == 0 else 8
        for i in range(n_core + 1):
            rows.append({
                "opportunity_id": f"OPP-{qi}{i}", "account_id": f"A{i}",
                "fiscal_quarter": q, "stage": "Closed Won",
                "realized_price": (4000.0 if qi == 1 else 1000.0)
                if i == 0 else 100.0,
                "is_outlier": i == 0,
            })
    opp = pd.DataFrame(rows)
    r = CHECKS["core_vs_headline_growth"](
        opp, pd.DataFrame(columns=["account_id"]),
        {"min_headline_growth_pct": 5, "max_core_growth_pct": -10})
    # headline 2000->4800 (+140%), core 900->800 (-11.1%)
    assert r["ok"], r["detail"]


def test_core_vs_headline_structural_without_outliers(tmp_path):
    criteria = {
        "definitions": {},
        "criteria": [
            {"id": "AC1", "name": "masking claim sans whales",
             "check": "core_vs_headline_growth",
             "params": {"min_headline_growth_pct": 5,
                        "max_core_growth_pct": -10}},
        ],
    }
    results, _ = _validate(tmp_path, base_cfg(), criteria)
    assert results[0]["verdict"] == "FAIL"
    assert "outlier_deals" in results[0]["detail"]


def test_outlier_share_by_quarter_concentrates_whales_late():
    """#17 lever: whales concentrated in the back half while core volume
    shrinks -> headline grows, core declines."""
    from syngen.validator.checks import CHECKS
    cfg = base_cfg(validate=False)
    cfg["opportunities"]["volume_multipliers"] = [1.0, 0.85]
    cfg["opportunities"]["outlier_deals"] = {
        "share_by_quarter": [0.01, 0.05],
        "multiplier": 25}
    frames = generate(validate_simulator_doc(cfg))
    opp = frames["opportunities"]
    r = CHECKS["core_vs_headline_growth"](
        opp, frames["accounts"],
        {"min_headline_growth_pct": 10, "max_core_growth_pct": -3})
    assert r["ok"], r["detail"]
    # replay consistency: is_outlier matches the per-quarter shares
    for label, share in zip(["FY26-Q1", "FY26-Q2"], [0.01, 0.05]):
        q = opp[opp["fiscal_quarter"] == label]
        assert q["is_outlier"].mean() == pytest.approx(share, abs=0.01)
