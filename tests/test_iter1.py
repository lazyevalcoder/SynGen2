"""M5 iteration 1: convergence intelligence (P0) + distribution extensions (P1)."""
import json
import copy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from syngen.config import ConfigError, validate_simulator_doc
from syngen.generator.engine import generate, generate_to_workbook
from syngen.llm.client import FakeLLM, LLMResponse
from syngen.phases.converge import LoopEscalation, _apply_changes, run_convergence
from syngen.session import Session
from syngen.validator.report import run_validation


def llm_json(obj):
    return LLMResponse(content=json.dumps(obj))


# --- P0: G14 allowlist --------------------------------------------------------

def test_apply_changes_blocks_plan_of_record_paths():
    cfg = {"time_model": {"fiscal_year": "FY26"}, "seed": 42,
           "output": {"workbook": "x"},
           "quota": {"by_segment": {}, "attainment_by_segment": None},
           "opportunities": {"win_rate": 0.3}}
    applied = _apply_changes(cfg, [
        {"path": "time_model.fiscal_year", "to": "FY27"},
        {"path": "seed", "to": 43},
        {"path": "output.workbook", "to": "y.xlsx"},
        {"path": "quota.by_segment.Enterprise", "to": [1]},
        {"path": "opportunities.win_rate", "to": 0.35},
    ])
    errs = {a["path"]: a.get("error", "") for a in applied}
    for p in ("time_model.fiscal_year", "seed", "output.workbook",
              "quota.by_segment.Enterprise"):
        assert "blocked" in errs[p], f"{p} should be blocked"
    assert "error" not in applied[-1]
    assert cfg["opportunities"]["win_rate"] == 0.35
    assert cfg["seed"] == 42 and cfg["time_model"]["fiscal_year"] == "FY26"


def test_apply_changes_allows_attainment_and_creates_through_nulls():
    """M5 live lesson: attainment is the legitimate raking knob, and leaf
    paths through explicit null containers must work."""
    cfg = {"quota": {"by_segment": {"E": [100]}, "attainment_by_segment":
                     {"E": 1.0}},
           "accounts": {"icp_sampling_weights_by_quarter": None},
           "opportunities": {}}
    applied = _apply_changes(cfg, [
        {"path": "quota.attainment_by_segment.E", "to": 0.95},
        {"path": "accounts.icp_sampling_weights_by_quarter.icp",
         "to": [1, 0.8]},
    ])
    assert all("error" not in a for a in applied), applied
    assert cfg["quota"]["attainment_by_segment"]["E"] == 0.95
    assert cfg["accounts"]["icp_sampling_weights_by_quarter"]["icp"] == [1, 0.8]


# --- P0: G4 margin-aware hardening --------------------------------------------

def _passing_cfg(tmp_path):
    """Config that trivially passes its criteria on iteration 1."""
    cfg = validate_simulator_doc({
        "seed": 7,
        "time_model": {
            "fiscal_year": "FY26",
            "quarter_labels": ["FY26-Q1", "FY26-Q2"],
            "quarter_end_dates": ["2026-03-31", "2026-06-30"],
        },
        "output": {"workbook": str(tmp_path / "ds.xlsx")},
        "accounts": {
            "count": 40,
            "regions": {"AMER": 0.6, "EMEA": 0.4},
            "segments": {"Enterprise": 0.5, "SMB": 0.5},
            "industries": ["Software"],
        },
        "opportunities": {
            "per_quarter": 400,
            "win_rate": 0.3,
            "win_rate_jitter": 0.005,
            "owners": ["A Rep"],
            "deal_duration_days": [10, 30],
            "close_clustering": {"share_in_end_of_quarter_window": 0.25},
            "deal_size_lognormal": {"median_usd": 50000, "sigma": 0.5},
            "discount": {
                "base_by_quarter": {"AMER": [10, 10], "EMEA": [12, 12]},
                "noise_sd_pp": 1.5,
                "end_of_quarter_boost_pp": 5,
                "end_of_quarter_window_days": 10,
                "min_pct": 0,
                "max_pct": 40,
            },
        },
    })
    return cfg


PASSING_CRITERIA = {
    "definitions": {},
    "criteria": [
        {"id": "AC1", "name": "flat win rate", "check": "win_rate_flat",
         "params": {"band_pp": 15}},
    ],
}


def _run_conv(session, tmp_path, client, cfg, **kw):
    sim_path = tmp_path / "simulator.json"
    crit_path = tmp_path / "criteria.json"
    sim_path.write_text(json.dumps(cfg), encoding="utf-8")
    crit_path.write_text(json.dumps(PASSING_CRITERIA), encoding="utf-8")
    kw.setdefault("thin_margin_pp", 99.0)  # everything counts as "thin"
    kw.setdefault("max_hardening_rounds", 1)
    kw.setdefault("max_iterations", 6)
    return run_convergence(session, client, sim_path, crit_path,
                           log_fn=lambda *_: None, **kw)


def test_hardening_round_runs_and_converges(tmp_path):
    session = Session.create(str(tmp_path / "sess"))
    noop = {"changes": [{"path": "opportunities.win_rate_jitter",
                         "from": 0.005, "to": 0.005}]}
    client = FakeLLM([llm_json(noop)])
    summary = _run_conv(session, tmp_path, client, _passing_cfg(tmp_path))
    assert summary["status"] == "converged"
    # the proposal call happened even though the delivered summary snapshots
    # the ORIGINAL all-pass state (a no-op hardening never beats it)
    assert len(client.calls) == 1, "one hardening round expected"
    assert "hardening" in summary.get("note", "")
    restored = json.loads((tmp_path / "simulator.json").read_text(
        encoding="utf-8"))
    assert restored["opportunities"]["win_rate_jitter"] == 0.005, \
        "disk must hold the best known-good config"


def test_failed_hardening_reverts_to_best(tmp_path):
    session = Session.create(str(tmp_path / "sess"))
    # per_quarter=0 empties the fact table -> win_rate_flat errors -> FAIL
    breaker = {"changes": [
        {"path": "opportunities.per_quarter", "from": 400, "to": 0},
    ]}
    client = FakeLLM([llm_json(breaker)])
    original = _passing_cfg(tmp_path)
    summary = _run_conv(session, tmp_path, client, copy.deepcopy(original))
    assert summary["status"] == "converged"

    # disk state reverted: simulator.json matches the pre-hardening config
    restored = json.loads((tmp_path / "simulator.json").read_text(
        encoding="utf-8"))
    assert restored["opportunities"]["per_quarter"] == 400, \
        "revert must restore the best known-good config to disk"


def test_no_thin_margins_skips_hardening(tmp_path):
    session = Session.create(str(tmp_path / "sess"))
    client = FakeLLM([])  # must never be called
    summary = _run_conv(session, tmp_path, client, _passing_cfg(tmp_path),
                        thin_margin_pp=0.0)
    assert summary["status"] == "converged"
    assert summary["llm_proposals"] == 0
    assert summary["thin_margins"] == []


# --- P1 engine extensions -----------------------------------------------------

def _ext_cfg(**overrides):
    cfg = {
        "seed": 42,
        "time_model": {
            "fiscal_year": "FY26",
            "quarter_labels": ["FY26-Q1", "FY26-Q2"],
            "quarter_end_dates": ["2026-03-31", "2026-06-30"],
        },
        "output": {"workbook": "output/ds.xlsx"},
        "accounts": {
            "count": 200,
            "regions": {"AMER": 0.5, "EMEA": 0.5},
            "segments": {"Enterprise": 0.5, "SMB": 0.5},
            "industries": ["Software"],
        },
        "opportunities": {
            "per_quarter": 300,
            "win_rate": 0.3,
            "win_rate_jitter": 0.005,
            "owners": ["A Rep"],
            "deal_duration_days": [10, 30],
            "close_clustering": {"share_in_end_of_quarter_window": 0.25},
            "deal_size_lognormal": {"median_usd": 40000, "sigma": 0.5},
            "discount": {
                "base_by_quarter": {"AMER": [10, 10], "EMEA": [10, 10]},
                "noise_sd_pp": 1.5,
                "end_of_quarter_boost_pp": 5,
                "end_of_quarter_window_days": 8,
                "min_pct": 0,
                "max_pct": 40,
            },
        },
    }
    cfg.update(overrides)
    return validate_simulator_doc(cfg)


def test_per_period_deal_size_medians():
    cfg = _ext_cfg(opportunities={
        **_ext_cfg(validate=False)["opportunities"],
        "deal_size_lognormal": {"medians_by_quarter": [60000, 24000],
                                "sigma": 0.3},
    })
    opp = generate(cfg)["opportunities"]
    won = opp[opp["stage"] == "Closed Won"]
    q1 = won[won["fiscal_quarter"] == "FY26-Q1"]["list_price"].mean()
    q2 = won[won["fiscal_quarter"] == "FY26-Q2"]["list_price"].mean()
    assert q1 > 55000 and q2 < 29000


def test_icp_flag_flows_to_both_sheets():
    cfg = _ext_cfg(accounts={**_ext_cfg(validate=False)["accounts"],
                             "icp_share": 0.4})
    frames = generate(cfg)
    acc_icp = frames["accounts"]["icp"].mean()
    assert 0.25 <= acc_icp <= 0.55
    assert "icp" in frames["opportunities"].columns
    # FK coherence: opp icp matches its account's icp
    merged = frames["opportunities"].merge(
        frames["accounts"][["account_id", "icp"]], on="account_id",
        suffixes=("", "_acc"))
    assert (merged["icp"] == merged["icp_acc"]).all()


def test_icp_sampling_weights_shift_pipeline_mix():
    """(#7) per-quarter ICP sampling weights steer low-ICP pipeline share."""
    cfg = _ext_cfg(accounts={**_ext_cfg(validate=False)["accounts"],
                             "icp_share": 0.5,
                             "icp_sampling_weights_by_quarter": {
                                 "icp": [1.0, 0.5],
                                 "non_icp": [1.0, 2.0]}})
    opp = generate(cfg)["opportunities"]
    shares = opp.groupby("fiscal_quarter")["icp"].apply(
        lambda s: (~s).mean() * 100)
    assert shares["FY26-Q2"] - shares["FY26-Q1"] > 15, \
        f"low-ICP share should rise sharply: {shares.to_dict()}"


def test_icp_sampling_weights_validation():
    cfg = _ext_cfg(validate=False)
    cfg["accounts"]["icp_sampling_weights_by_quarter"] = {"icp": [1.0]}
    with pytest.raises(ConfigError, match="non_icp"):
        validate_simulator_doc(cfg)


def test_default_icp_share_is_neutral_zero():
    frames = generate(_ext_cfg())
    assert not frames["accounts"]["icp"].any()


def test_segment_mix_shift_across_quarters():
    cfg = _ext_cfg(accounts={**_ext_cfg(validate=False)["accounts"],
                             "segments": {
                                 "Enterprise": {"weights_by_quarter":
                                                [0.8, 0.2]},
                                 "SMB": {"weights_by_quarter": [0.2, 0.8]}}})
    opp = generate(cfg)["opportunities"]
    shares = opp.groupby(["fiscal_quarter", "segment"]).size().unstack()
    q1_ent = shares.loc["FY26-Q1", "Enterprise"] / shares.loc["FY26-Q1"].sum()
    q2_ent = shares.loc["FY26-Q2", "Enterprise"] / shares.loc["FY26-Q2"].sum()
    assert q1_ent > 0.65 and q2_ent < 0.35


def test_outlier_deals_create_concentration_with_identity():
    cfg = _ext_cfg(opportunities={
        **_ext_cfg(validate=False)["opportunities"],
        "outlier_deals": {"share": 0.02, "multiplier": 20},
    })
    opp = generate(cfg)["opportunities"]
    ident = (opp["realized_price"]
             - (opp["list_price"] * (1 - opp["discount_pct"] / 100)).round(2))
    assert ident.abs().max() <= 0.011, "identity must survive whale scaling"
    top = opp["realized_price"].nlargest(10).min()
    typical = opp["realized_price"].median()
    assert top > typical * 5, "whales should tower over typical deals"


def test_prior_year_labels_six_quarters_work(tmp_path):
    cfg = _ext_cfg(time_model={
        "fiscal_year": "FY25-FY26",
        "quarter_labels": ["FY25-Q3", "FY25-Q4", "FY26-Q1",
                           "FY26-Q2", "FY26-Q3", "FY26-Q4"],
        "quarter_end_dates": ["2025-09-30", "2025-12-31", "2026-03-31",
                              "2026-06-30", "2026-09-30", "2026-12-31"],
    }, opportunities={
        **_ext_cfg(validate=False)["opportunities"],
        "discount": {"base_by_quarter": {"AMER": [10] * 6, "EMEA": [11] * 6},
                     "noise_sd_pp": 1.5, "end_of_quarter_boost_pp": 5,
                     "end_of_quarter_window_days": 8,
                     "min_pct": 0, "max_pct": 40},
    })
    frames = generate(cfg)
    assert frames["opportunities"]["fiscal_quarter"].nunique() == 6
    assert len(frames["quarterly_summary"]) == 6


# --- P1 checks: both directions -----------------------------------------------

TWO_Q_CAL = {"FY26-Q1": "2026-03-31", "FY26-Q2": "2026-06-30"}

CRIT_SIZE_DECLINE = {"definitions": {}, "criteria": [
    {"id": "AC30", "name": "sizes shrink", "check": "deal_size_trend",
     "params": {"target_change_pct": -50, "tolerance_pp": 8,
                "quarter_ends": TWO_Q_CAL}}]}
CRIT_ICP_SHIFT = {"definitions": {}, "criteria": [
    {"id": "AC31", "name": "low-ICP share rises", "check": "icp_creation_shift",
     "params": {"min_increase_pp": 10, "quarter_ends": TWO_Q_CAL}}]}
CRIT_CONCENTRATION = {"definitions": {}, "criteria": [
    {"id": "AC32", "name": "whale concentration", "check": "revenue_concentration",
     "params": {"top_n": 5, "min_top_share_pct": 25,
                "quarter_ends": TWO_Q_CAL}}]}


def _validate(tmp_path, cfg, criteria):
    cfg["output"]["workbook"] = str(tmp_path / "ds.xlsx")
    _, wb = generate_to_workbook(cfg)
    crit = tmp_path / "criteria.json"
    crit.write_text(json.dumps(criteria), encoding="utf-8")
    return run_validation(wb, crit)


def test_deal_size_decline_lands(tmp_path):
    cfg = _ext_cfg(opportunities={
        **_ext_cfg(validate=False)["opportunities"],
        "deal_size_lognormal": {"medians_by_quarter": [60000, 30000],
                                "sigma": 0.3},
    })
    results, ok = _validate(tmp_path, cfg, CRIT_SIZE_DECLINE)
    assert ok, results[0]["detail"]


def test_flat_sizes_fail_decline_check(tmp_path):
    results, ok = _validate(tmp_path, _ext_cfg(), CRIT_SIZE_DECLINE)
    assert not ok and results[0]["verdict"] == "FAIL"


def test_icp_shift_check_two_directions():
    """Direct frames: the check measures the low-ICP creation-share shift
    between boundary quarters, both directions."""
    from syngen.validator.checks import CHECKS
    cal = {"FY26-Q1": "2026-03-31", "FY26-Q2": "2026-06-30"}

    def frame(q1_low_icp_pct, q2_low_icp_pct, n=200):
        rows = []
        for label, pct in (("FY26-Q1", q1_low_icp_pct),
                           ("FY26-Q2", q2_low_icp_pct)):
            for i in range(n):
                rows.append({"fiscal_quarter": label, "icp": i >= n * pct / 100,
                             "stage": "Closed Won"})
        return pd.DataFrame(rows)

    rising = CHECKS["icp_creation_shift"](
        frame(10, 40), pd.DataFrame(),
        {"min_increase_pp": 20, "quarter_ends": cal})
    assert rising["ok"] and rising["margin"] > 0

    falling = CHECKS["icp_creation_shift"](
        frame(40, 10), pd.DataFrame(),
        {"min_increase_pp": 20, "quarter_ends": cal})
    assert not falling["ok"] and falling["margin"] < 0


def test_concentration_check_two_directions(tmp_path):
    whales = _ext_cfg(opportunities={
        **_ext_cfg(validate=False)["opportunities"],
        "outlier_deals": {"share": 0.02, "multiplier": 25},
    })
    results, ok = _validate(tmp_path, whales, CRIT_CONCENTRATION)
    assert ok, results[0]["detail"]

    results, ok = _validate(tmp_path, _ext_cfg(), CRIT_CONCENTRATION)
    assert not ok and results[0]["verdict"] == "FAIL"


# --- config validation ---------------------------------------------------------

def test_medians_length_mismatch_rejected():
    cfg = _ext_cfg(validate=False)
    cfg["opportunities"]["deal_size_lognormal"]["medians_by_quarter"] = [1]
    with pytest.raises(ConfigError, match="one value per quarter"):
        validate_simulator_doc(cfg)


def test_mix_shift_weights_must_sum_to_one():
    cfg = _ext_cfg(validate=False)
    cfg["accounts"]["segments"] = {
        "Enterprise": {"weights_by_quarter": [0.8, 0.8]},
        "SMB": {"weights_by_quarter": [0.2, 0.9]},  # Q2 sums 1.7
    }
    with pytest.raises(ConfigError, match="sum"):
        validate_simulator_doc(cfg)


def test_outlier_config_bounds():
    cfg = _ext_cfg(validate=False)
    cfg["opportunities"]["outlier_deals"] = {"share": 0.9, "multiplier": 5}
    with pytest.raises(ConfigError, match="between 0 and 0.5"):
        validate_simulator_doc(cfg)
