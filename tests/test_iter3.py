"""M5 iteration 3: pre-flight calibration + P4 open-pipeline state machine.

Golden-anchor rule: without a pipeline block the engine output is
unchanged; all new randomness lives on the [seed, 5, qi] stream.
"""
import copy

import numpy as np
import pandas as pd
import pytest

from syngen.config import ConfigError, validate_simulator_doc
from syngen.generator.engine import build_accounts, build_opportunities, \
    generate
from syngen.linter import has_blocking, structure_findings
from syngen.validator import checks


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
            "count": 50,
            "regions": {"AMER": 0.6, "EMEA": 0.4},
            "segments": {"Enterprise": 0.5, "SMB": 0.5},
            "industries": ["Tech"],
        },
        "opportunities": {
            "per_quarter": 150,
            "win_rate": 0.3,
            "win_rate_jitter": 0.02,
            "owners": ["A"],
            "deal_duration_days": [20, 40],
            "close_clustering": {"share_in_end_of_quarter_window": 0.25},
            "deal_size_lognormal": {"median_usd": 40000, "sigma": 0.6},
            "discount": {
                "base_by_quarter": {"AMER": [10] * 4, "EMEA": [12] * 4},
                "noise_sd_pp": 2.5,
                "end_of_quarter_boost_pp": 6,
                "end_of_quarter_window_days": 10,
                "min_pct": 0, "max_pct": 35},
        },
    }
    cfg.update(over)
    return validate_simulator_doc(cfg)


PIPE = {
    "stage_names": ["Discovery", "Proposal"],
    "share_open_by_quarter": [0.2, 0.25, 0.3, 0.35],
    "slippage_rate_by_quarter": [0.1, 0.2, 0.35, 0.5],
}


def make_engine_data(cfg):
    acc = build_accounts(cfg, np.random.default_rng(cfg["seed"]))
    return build_opportunities(cfg, acc, np.random.default_rng(cfg["seed"]))


def test_no_pipeline_block_output_unchanged():
    """Golden-anchor safety: absent pipeline block -> no lifecycle columns."""
    opp = make_engine_data(base_cfg())
    assert "expected_close_date" not in opp.columns
    assert set(opp["stage"].unique()) == {"Closed Won", "Closed Lost"}


def test_open_pipeline_rows_and_history():
    cfg = base_cfg(pipeline=PIPE)
    o1 = make_engine_data(cfg)
    o2 = make_engine_data(cfg)
    pd.testing.assert_frame_equal(o1, o2)  # named-stream reproducibility
    open_rows = o1[~o1["stage"].isin(["Closed Won", "Closed Lost"])]
    total = len(o1)
    assert len(open_rows) == int(round(total * np.mean(
        PIPE["share_open_by_quarter"])))
    assert set(open_rows["stage"]) <= set(PIPE["stage_names"])
    assert open_rows["close_date"].isna().all()
    assert open_rows["expected_close_date"].notna().all()
    hist = o1.attrs["stage_history"]
    assert len(hist) == len(open_rows)
    assert list(hist.columns) == ["opportunity_id", "stage", "entered_date",
                                  "fiscal_quarter"]


def test_slippage_pushes_expected_close_past_quarter_end():
    pipe = copy.deepcopy(PIPE)
    pipe["slippage_rate_by_quarter"] = [0.0, 0.0, 1.0, 1.0]
    cfg = base_cfg(pipeline=pipe)
    opp = make_engine_data(cfg)
    qends = {"FY26-Q1": "2026-03-31", "FY26-Q2": "2026-06-30",
             "FY26-Q3": "2026-09-30", "FY26-Q4": "2026-12-31"}
    open_rows = opp[~opp["stage"].isin(["Closed Won", "Closed Lost"])]
    ec = pd.to_datetime(open_rows["expected_close_date"])
    qe = pd.to_datetime(open_rows["fiscal_quarter"].map(qends))
    slipped = (ec > qe).groupby(open_rows["fiscal_quarter"]).mean()
    assert slipped["FY26-Q1"] == 0.0
    assert slipped["FY26-Q4"] > 0.9


def test_raking_and_quota_checks_immune_to_open_rows():
    """Open deals must never count as closed-won revenue anywhere."""
    cfg = base_cfg(pipeline=PIPE, quota={
        "by_segment": {"SMB": [200_000] * 4}})
    frames = generate(cfg)
    opp = frames["opportunities"]
    open_rows = opp[~opp["stage"].isin(["Closed Won", "Closed Lost"])]
    assert len(open_rows) > 0
    won = opp[opp["stage"] == "Closed Won"]
    smb_won = won[won["segment"] == "SMB"]
    target = 200_000 * 1.0
    # SMB has all the volume here; raking hits its stratum exactly
    assert abs(smb_won[smb_won["fiscal_quarter"] == "FY26-Q2"]
               ["realized_price"].sum() - target) < 1.0


def test_structure_gate_accepts_engine_output_with_pipeline(tmp_path):
    from syngen.generator.engine import generate_to_workbook
    cfg = base_cfg(pipeline=PIPE)
    cfg["output"]["workbook"] = str(tmp_path / "wb.xlsx")
    _, wb = generate_to_workbook(cfg)
    findings = structure_findings(wb, cfg=cfg)
    assert not has_blocking(findings), findings


# --- check functions ------------------------------------------------------

QENDS = {"FY26-Q1": "2026-03-31", "FY26-Q2": "2026-06-30"}


def mk_opp(slip_q2=0.8):
    rows = []
    for qi, label in enumerate(["FY26-Q1", "FY26-Q2"]):
        for i in range(40):
            # first 30 rows are old (stale), last 10 are recent
            created = pd.Timestamp("2025-11-20") if i < 30 else \
                pd.Timestamp("2026-06-15")
            slipped = i / 40 < slip_q2 if qi == 1 else i / 40 < 0.1
            rows.append({
                "opportunity_id": f"P{qi}-{i}",
                "account_id": f"ACC-{i % 8}",
                "fiscal_quarter": label,
                "created_date": created,
                "stage": "Discovery",
                "realized_price": 10000.0,
                "expected_close_date":
                    pd.Timestamp(QENDS[label]) + pd.Timedelta(
                        days=30 if slipped else -10),
            })
    return pd.DataFrame(rows)


P = {"quarter_ends": QENDS}


def test_stage_aging_both_directions():
    opp = mk_opp()
    ok = checks.check_stage_aging(opp, None, {**P, "stale_threshold_days": 365,
                                              "max_stale_share_pct": 90})
    assert ok["ok"], ok
    tight = checks.check_stage_aging(opp, None, {**P, "stale_threshold_days": 60,
                                                 "max_stale_share_pct": 10})
    assert not tight["ok"]
    closed_only = opp[opp["stage"] == "Closed Won"]
    r = checks.check_stage_aging(closed_only, None,
                                 {**P, "stale_threshold_days": 100,
                                  "max_stale_share_pct": 10})
    assert r.get("structural")


def test_slippage_trend_both_directions():
    rising = mk_opp(slip_q2=0.9)
    ok = checks.check_slippage_trend(rising, None, {**P, "min_increase_pp": 20})
    assert ok["ok"], ok
    flat = mk_opp(slip_q2=0.1)
    anti = checks.check_slippage_trend(flat, None,
                                       {**P, "min_increase_pp": 20})
    assert not anti["ok"]
    plain = rising.drop(columns=["expected_close_date"])
    r = checks.check_slippage_trend(plain, None,
                                    {**P, "min_increase_pp": 5})
    assert r.get("structural")


def test_coverage_ratio_structural_and_pass():
    quota = pd.DataFrame([
        {"plan_unit_type": "segment", "plan_unit": "SMB",
         "fiscal_quarter": "FY26-Q2", "target_realized_usd": 100000.0}])
    opp = mk_opp()  # 80 open rows x $10k = $800k value in Q2 window
    params = {**P, "_quota_df": quota, "quarter": "FY26-Q2",
              "min_multiple": 2.0}
    ok = checks.check_coverage_ratio(opp, None, params)
    assert ok["ok"], ok
    steep = checks.check_coverage_ratio(opp, None, {**params,
                                                    "min_multiple": 50})
    assert not steep["ok"]
    no_quota = checks.check_coverage_ratio(
        opp, None, {"quarter_ends": QENDS, "quarter": "FY26-Q2",
                    "min_multiple": 1.0})
    assert no_quota.get("structural")


def test_pipeline_concentration():
    opp = mk_opp()
    # fixture spreads over 8 accounts evenly -> top-2 ~ 25%
    ok = checks.check_pipeline_concentration(opp, None, {
        **P, "top_n_accounts": 2, "min_top_share_pct": 20})
    assert ok["ok"], ok
    anti = checks.check_pipeline_concentration(opp, None, {
        **P, "top_n_accounts": 2, "min_top_share_pct": 60})
    assert not anti["ok"]


def test_validation_pipeline_block_errors():
    with pytest.raises(ConfigError):  # share curve wrong length
        base_cfg(pipeline={"stage_names": ["D"],
                           "share_open_by_quarter": [0.2]})
    with pytest.raises(ConfigError):  # slippage > 1
        base_cfg(pipeline={"stage_names": ["D"], "share_open_by_quarter":
                           [0.2] * 4, "slippage_rate_by_quarter":
                           [0.5, 0.5, 0.5, 1.5]})
    with pytest.raises(ConfigError):  # weights length mismatch
        base_cfg(pipeline={"stage_names": ["D", "P"],
                           "share_open_by_quarter": [0.2] * 4,
                           "stage_weights": [1.0]})
