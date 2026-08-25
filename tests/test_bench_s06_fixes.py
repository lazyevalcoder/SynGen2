"""Bench s06 defect fixes: D1 planning overwrite bug, D2 measured
quota-vs-potential scaling remedy."""
import json

from syngen.phases.converge import _remedy_quota_potential
from syngen.phases.preflight import autocalibrate

import pandas as pd


def crit(cid, check, **params):
    return {"id": cid, "name": cid, "check": check, "params": params,
            "classification": "parametric", "source_claim": cid}


def base_cfg():
    return {
        "seed": 42,
        "time_model": {
            "fiscal_year": "FY26",
            "quarter_labels": ["FY26-Q1", "FY26-Q2", "FY26-Q3", "FY26-Q4"],
            "quarter_end_dates": ["2026-03-31", "2026-06-30",
                                  "2026-09-30", "2026-12-31"],
        },
        "output": {"workbook": "output/dataset.xlsx"},
        "accounts": {
            "count": 60,
            "regions": {"AMER": 1.0},
            "segments": {"Enterprise": 0.5, "Mid-Market": 0.3, "SMB": 0.2},
            "industries": ["Software"],
        },
        "opportunities": {
            "per_quarter": 300,
            "win_rate": 0.27,
            "win_rate_jitter": 0.005,
            "owners": ["A", "B"],
            "deal_duration_days": [20, 90],
            "close_clustering": {"share_in_end_of_quarter_window": 0.25},
            "deal_size_lognormal": {"median_usd": 45000, "sigma": 0.8},
            "discount": {
                "base_by_quarter": {"AMER": [12, 12, 12, 12]},
                "noise_sd_pp": 3,
                "end_of_quarter_boost_pp": 6.5,
                "end_of_quarter_window_days": 14,
                "min_pct": 0, "max_pct": 40,
            },
        },
        "quota": {
            "by_segment": {"Enterprise": [2_400_000] * 4,
                           "Mid-Market": [900_000] * 4,
                           "SMB": [600_000] * 4},
        },
    }


def test_d1_planning_never_overwrites_unit_targets():
    """Bench s06: the company-wide branch used to stomp Enterprise back to
    1.00 immediately after the criterion pinned it to 0.95."""
    cfg = base_cfg()
    doc = {"definitions": {}, "criteria": [
        crit("AC1", "revenue_vs_plan", segment="Enterprise",
             target_pct=95, band_pct=2),
        crit("AC3", "revenue_vs_plan", segment="_all_",
             target_pct=100, band_pct=2),
    ]}
    autocalibrate(cfg, doc)
    att = cfg["quota"]["attainment"]
    assert abs(att["Enterprise"] - 0.95) < 0.01, \
        f"unit target stomped by company-wide branch: {att}"


def test_d2_measured_quota_potential_scaling(tmp_path):
    """Plans scale against MEASURED account potential so the ratio lands
    exactly on the criterion's target."""
    cfg = base_cfg()
    # measured market: Enterprise potential totals 20M -> drafted 2.4M/qtr
    # = 9.6M/yr = 48% of market; criterion wants ~120%
    accounts = pd.DataFrame({
        "account_id": [f"A{i}" for i in range(10)],
        "segment": ["Enterprise"] * 10,
        "market_potential_usd": [2_000_000.0] * 10,
    })
    wb = tmp_path / "ds.xlsx"
    with pd.ExcelWriter(wb, engine="openpyxl") as w:
        accounts.to_excel(w, sheet_name="accounts", index=False)

    doc = {"definitions": {}, "criteria": [
        crit("AC4", "quota_vs_potential", dimension="segment",
             unit="Enterprise", target_ratio_pct=120, band_pp=10)]}
    results = [{"id": "AC4", "verdict": "FAIL", "margin": -90.0}]

    class _S:
        def log(self, *_):
            pass

    fixes = _remedy_quota_potential(cfg, doc, results, wb,
                                    lambda *_: None, _S())
    assert fixes, "expected the scaling remedy to fire"
    curve = cfg["quota"]["by_segment"]["Enterprise"]
    total = sum(curve)
    ratio = total / 20_000_000 * 100
    assert abs(ratio - 120) < 1, f"scaled ratio {ratio:.1f}% != ~120%"
    # untouched units keep their plans
    assert cfg["quota"]["by_segment"]["Mid-Market"] == [900_000] * 4


def test_d2_remedy_is_none_when_no_qp_criterion_fails(tmp_path):
    cfg = base_cfg()
    results = [{"id": "AC1", "verdict": "FAIL", "margin": -1.0}]
    out = _remedy_quota_potential(cfg, {"criteria": []}, results,
                                  tmp_path / "nope.xlsx",
                                  lambda *_: None, object())
    assert out is None  # cheap exit: no excel read attempted
