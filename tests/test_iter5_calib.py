"""M5 iter 5 item 2: auto-calibration extended to iter-4 primitives (R2).

Every amend-loop algebra step the D/E landings did by hand must now be a
deterministic pre-flight pass: block synthesis for missing structural
blocks, effective-capacity ramping solve, and the core/headline whale
sizing. Proofs run the ENGINE end-to-end, not just config inspection.
"""
import json

from syngen.config import validate_simulator_doc
from syngen.generator.engine import generate_to_workbook
from syngen.phases.preflight import autocalibrate, calibrate
from syngen.validator.report import run_validation


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
            "regions": {"AMER": 0.5, "EMEA": 0.3, "APAC": 0.2},
            "segments": {"Enterprise": 0.4, "Mid-Market": 0.35, "SMB": 0.25},
            "industries": ["Software", "Retail"],
            "territories": {"West": ["AMER"], "East": ["EMEA", "APAC"]},
        },
        "opportunities": {
            "per_quarter": 300,
            "win_rate": 0.27,
            "win_rate_jitter": 0.005,
            "owners": ["A Rep", "B Rep", "C Rep"],
            "deal_duration_days": [20, 90],
            "close_clustering": {"share_in_end_of_quarter_window": 0.25},
            "deal_size_lognormal": {"median_usd": 45000, "sigma": 0.8},
            "discount": {
                "base_by_quarter": {
                    "AMER": [12, 12, 12, 12],
                    "EMEA": [12, 12, 12, 12],
                    "APAC": [12, 12, 12, 12],
                },
                "noise_sd_pp": 3,
                "end_of_quarter_boost_pp": 6.5,
                "end_of_quarter_window_days": 14,
                "min_pct": 0, "max_pct": 40,
            },
        },
    }


def crit(cid, check, **params):
    return {"id": cid, "name": cid, "check": check, "params": params,
            "classification": "parametric", "source_claim": cid}


def test_calibrate_flags_missing_iter4_blocks_as_hard():
    cfg = base_cfg()
    doc = {"definitions": {}, "criteria": [
        crit("AC1", "unowned_account_share", min_unowned_share_pct=25),
        crit("AC2", "forecast_vs_actual", target_pct=109, band_pp=3),
    ]}
    findings = calibrate(cfg, doc)
    hard = {f["criterion"] for f in findings
            if f["severity"] == "HARD" and f["rule"] == "PF1"}
    assert hard == {"AC1", "AC2"}


def test_blocks_pass_synthesizes_all_missing_blocks():
    cfg = base_cfg()
    doc = {"definitions": {}, "criteria": [
        crit("AC1", "unowned_account_share", min_unowned_share_pct=25),
        crit("AC2", "post_change_revenue_decline", min_gap_pp=10),
        crit("AC3", "commit_no_engagement_share", min_share_pct=40),
        crit("AC4", "activity_potential_misalignment", min_gap_pp=15),
        crit("AC5", "elasticity_differential", min_gap_pp=8),
    ]}
    fixes = autocalibrate(cfg, doc)
    assert cfg["ownership"]["unowned_share_by_quarter"][-1] >= 0.25 + 0.05
    assert cfg["ownership"]["win_rate_multiplier_after_change"] < 1
    assert cfg["activity"]["potential_tilt"] < 0
    assert cfg["forecast"]["low_activity_bias"] > 0
    assert cfg["pricing_response"]["elasticity"] < 0
    assert any("ownership" in f for f in fixes)
    # synthesized blocks must be schema-valid and clear the P1 findings
    validate_simulator_doc(json.loads(json.dumps(cfg)))
    assert not [f for f in calibrate(cfg, doc) if f["severity"] == "HARD"]


def test_capacity_solver_hits_effective_capacity_target(tmp_path):
    cfg = base_cfg()
    doc = {"definitions": {}, "criteria": [
        crit("AC1", "effective_capacity", target_pct=87, band_pp=3),
    ]}
    fixes = autocalibrate(cfg, doc)
    spec = cfg["capacity"]["by_territory"]["West"]
    P = spec["headcount_plan"][0]
    A = spec["headcount_actual"][0]
    R = spec["ramping_reps_by_quarter"][0]
    p = spec["ramp_productivity_pct"]
    eff = ((A - R) + R * p / 100.0) / P * 100.0
    assert abs(eff - 87) <= 3 * 0.6
    assert any("effective capacity" in f for f in fixes)


def test_core_vs_headline_recipe_generates_a_landing_dataset(tmp_path):
    """The full #17 recipe: criterion -> sized blocks -> generated data ->
    PASS, with no human in the loop."""
    cfg = base_cfg()
    doc = {"definitions": {}, "criteria": [
        crit("AC1", "core_vs_headline_growth",
             min_headline_growth_pct=5, max_core_growth_pct=-8),
        crit("AC2", "data_sanity", max_discount_pct=70),
    ]}
    fixes = autocalibrate(cfg, doc)
    assert any("outlier_deals" in f or "volume_multipliers" in f
               for f in fixes)
    assert not cfg.get("quota"), \
        "core_vs_headline sizing must NOT synthesize a quota block"
    validate_simulator_doc(json.loads(json.dumps(cfg)))
    out = tmp_path / "ds.xlsx"
    cfg["output"]["workbook"] = str(out).replace("\\", "/")
    generate_to_workbook(cfg)
    cpath = tmp_path / "criteria.json"
    cpath.write_text(json.dumps(doc), encoding="utf-8")
    results, _ = run_validation(out, cpath)
    ac1 = next(r for r in results if r["id"] == "AC1")
    assert ac1["verdict"] == "PASS", f"core_vs_headline failed: {ac1}"
