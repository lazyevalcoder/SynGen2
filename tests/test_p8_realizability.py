"""P8 realizability guarantee: acceptance is a guarantee, not a hope.

Regressions for the class the 21/22/25 re-fly exposed:

- S21.2 the concentration solver must solve WITHIN the sigma domain and
  report infeasibility instead of writing an out-of-domain config.
- S24.2/S25.2 concentration targets above the deal-size-tail ceiling are
  flagged at the cross-lint so criteria can be re-expressed.
- S25.1 headline growth above the plan-pinned ceiling is flagged.
- S25.3 vacuous (cannot-fail) thresholds are hard findings at Gate 1.
- S25.4 a persistent Gate-1 consistency conflict is recoverable through
  the bounded, claim-preserving rework judge.
- S21.1 the structure gate tolerates column ORDER (only presence matters).
- S22.1 a plan unit with no account potential is a STRUCTURAL mismatch.
"""
import json

import pandas as pd
import pytest

from syngen.config import validate_simulator_doc
from syngen.llm.client import FakeLLM, LLMResponse
from syngen.packs.revops import envelope
from syngen.packs.revops.checks import check_quota_vs_potential
from syngen.phases import rework
from syngen.phases.criteria_lint import cross_lint, lint_criteria_internal
from syngen.phases.preflight import autocalibrate

from test_p5_envelope import base_cfg, crit
from test_pipeline import AUDIT_COVERED, CRITERIA, PRECHECK
from test_entity_schemas import ALL_BLOCKS_CFG


def llm_json(obj):
    return LLMResponse(content=json.dumps(obj))


def _big_cfg():
    """A config where the top-N open-pipeline share is genuinely bounded:
    many accounts, many open deals, so the deal-size tail caps out well
    below an extreme target (the scenario_21 shape)."""
    cfg = json.loads(json.dumps(ALL_BLOCKS_CFG))
    cfg["accounts"]["count"] = 1200
    cfg["opportunities"]["per_quarter"] = 900
    cfg["opportunities"]["volume_multipliers"] = [1.0, 1.0, 1.0, 1.0]
    cfg["pipeline"]["share_open_by_quarter"] = [0.2, 0.3, 0.4, 0.5]
    return validate_simulator_doc(cfg)


# --- envelope ---------------------------------------------------------------


def test_pipeline_ceiling_is_monotone_in_sigma():
    cfg = base_cfg()
    lo = envelope.pipeline_top_share(cfg, 0.6, 5)
    hi = envelope.pipeline_top_share(cfg, envelope.SIGMA_CAP, 5)
    assert lo is not None and hi is not None
    assert hi >= lo


def test_pipeline_estimator_includes_outlier_lever():
    """The outlier multiplier is the engine's dominant concentration lever;
    the estimator must reflect it (sigma-only under-predicted 52% vs 96.9%)."""
    cfg = _big_cfg()
    base = envelope.pipeline_top_share(cfg, 2.0, 5)
    boosted = envelope.pipeline_top_share(cfg, 2.0, 5, outlier_mult=500.0)
    assert base is not None and boosted is not None
    assert boosted > base


# --- S21.2 solver discipline -------------------------------------------------


def test_concentration_solver_reachable_stays_in_domain():
    cfg = _big_cfg()
    doc = {"criteria": [crit("AC4", "pipeline_concentration",
                             top_n_accounts=5, min_top_share_pct=50)]}
    fixes = autocalibrate(cfg, doc)
    sigma = float(cfg["opportunities"]["deal_size_lognormal"]["sigma"])
    assert 0.0 < sigma <= envelope.SIGMA_CAP
    got = envelope.pipeline_top_share(cfg, sigma, 5)
    assert got >= 0.50 - 1e-9, f"predicted {got} (fixes={fixes})"


def test_concentration_solver_uses_outlier_lever_when_sigma_capped():
    """When the target exceeds what sigma alone can reach, the solver raises
    the (unbounded) outlier multiplier instead of writing an invalid config."""
    cfg = _big_cfg()
    cfg["accounts"]["count"] = 5000  # many accounts -> sigma alone cannot
    doc = {"criteria": [crit("AC4", "pipeline_concentration",
                             top_n_accounts=5, min_top_share_pct=90)]}
    fixes = autocalibrate(cfg, doc)
    sigma = float(cfg["opportunities"]["deal_size_lognormal"]["sigma"])
    assert 0.0 < sigma <= envelope.SIGMA_CAP
    mult = cfg["opportunities"].get("outlier_deals", {}).get("multiplier")
    got = envelope.pipeline_top_share(cfg, sigma, 5, outlier_mult=mult)
    assert got >= 0.90 - 1e-9, f"predicted {got} (fixes={fixes})"
    validate_simulator_doc(cfg)


def test_concentration_solver_output_validates():
    cfg = _big_cfg()
    doc = {"criteria": [crit("AC4", "pipeline_concentration",
                             top_n_accounts=5, min_top_share_pct=90)]}
    autocalibrate(cfg, doc)
    validate_simulator_doc(cfg)  # must not raise


# --- S25.1 growth feasibility (concentration is NOT gated: unbounded lever) --


def test_cross_lint_does_not_false_kill_concentration():
    findings = cross_lint(_big_cfg(), {"criteria": [
        crit("AC4", "pipeline_concentration",
             top_n_accounts=5, min_top_share_pct=95)]})
    assert not any("unreachable" in f for f in findings), findings


def test_cross_lint_growth_works_without_products_or_quota():
    """Growth feasibility must not be skipped for pipeline/outlier-only
    configs (the products/quota branches early-return in the tier checks)."""
    cfg = base_cfg()
    cfg.pop("products", None)
    cfg.pop("quota", None)
    findings = cross_lint(cfg, {"criteria": [
        crit("AC2", "core_vs_headline_growth",
             min_headline_growth_pct=50, max_core_growth_pct=-5)]})
    assert any("unreachable" in f for f in findings), findings


def test_cross_lint_coordinate_only_excludes_feasibility():
    """P8: the pre-calibration pass must check coordinates only, so growth
    feasibility (which needs synthesized blocks) is not run too early."""
    cfg = base_cfg()
    doc = {"criteria": [crit("AC2", "core_vs_headline_growth",
                             min_headline_growth_pct=50,
                             max_core_growth_pct=-5)]}
    assert not any("unreachable" in f
                   for f in cross_lint(cfg, doc, feasibility=False))
    assert any("unreachable" in f
               for f in cross_lint(cfg, doc, feasibility=True))


def test_cross_lint_flags_unreachable_growth():
    findings = cross_lint(base_cfg(), {"criteria": [
        crit("AC2", "core_vs_headline_growth",
             min_headline_growth_pct=50, max_core_growth_pct=-5)]})
    assert any("unreachable" in f and "headline" in f for f in findings)


def test_cross_lint_allows_flat_growth():
    findings = cross_lint(base_cfg(), {"criteria": [
        crit("AC2", "core_vs_headline_growth",
             min_headline_growth_pct=0, max_core_growth_pct=-5)]})
    assert not any("unreachable" in f for f in findings)


# --- S25.3 vacuous thresholds ------------------------------------------------


def test_vacuous_gap_threshold_is_hard():
    hard, _ = lint_criteria_internal({"criteria": [
        crit("AC5", "end_of_quarter_effect", min_gap_pp=0)]})
    assert any("vacuous" in h for h in hard)


def test_vacuous_price_cap_is_hard():
    hard, _ = lint_criteria_internal({"criteria": [
        crit("AC4", "avg_price_by_tier", tier="core",
             max_avg_realized_usd=1_000_000_000)]})
    assert any("vacuous" in h for h in hard)


def test_meaningful_threshold_is_not_flagged():
    hard, _ = lint_criteria_internal({"criteria": [
        crit("AC5", "end_of_quarter_effect", min_gap_pp=10),
        crit("AC4", "pipeline_concentration",
             top_n_accounts=5, min_top_share_pct=50)]})
    assert not any("vacuous" in h for h in hard)


# --- S25.4 Gate-1 consistency recovery --------------------------------------


def _conflicting_criteria():
    return {"definitions": {}, "criteria": [
        crit("AC1", "revenue_vs_plan", segment="_all_", dimension="segment",
             target_pct=94, band_pct=2),
        crit("AC2", "revenue_vs_plan", segment="_all_", dimension="segment",
             target_pct=100, band_pct=2),
    ]}


def test_gate1_consistency_recovered_by_judge():
    conflicting = _conflicting_criteria()
    hard, _ = lint_criteria_internal(conflicting)
    assert hard, "fixture must be inconsistent"
    judge = {"action": "rework_criteria", "scope": ["AC1", "AC2"],
             "guidance": "overlap the bands", "reason": "jointly unsatisfiable"}
    client = FakeLLM([llm_json(judge), llm_json(CRITERIA),
                      llm_json(AUDIT_COVERED)])
    doc, ok, directives = rework.recover_criteria_consistency(
        client, "story", conflicting, PRECHECK, "", hard, 2,
        log_fn=lambda *a, **k: None)
    assert ok is True
    assert not lint_criteria_internal(doc)[0]
    assert directives and directives[0]["action"] == "rework_criteria"


def test_gate1_consistency_gives_up_when_judge_escalates():
    conflicting = _conflicting_criteria()
    hard, _ = lint_criteria_internal(conflicting)
    judge = {"action": "escalate", "scope": [], "guidance": "",
             "reason": "no revision helps"}
    client = FakeLLM([llm_json(judge)])
    doc, ok, directives = rework.recover_criteria_consistency(
        client, "story", conflicting, PRECHECK, "", hard, 2,
        log_fn=lambda *a, **k: None)
    assert ok is False
    assert doc is conflicting


# --- S21.1 structure gate: order tolerance ----------------------------------


def test_structure_gate_tolerates_column_order(tmp_path):
    from syngen.linter import expected_sheets_for, structure_findings
    cfg = base_cfg()
    expected = expected_sheets_for(cfg)
    path = tmp_path / "wb.xlsx"
    with pd.ExcelWriter(path) as xw:
        for sheet, cols in expected.items():
            if not cols:
                df = pd.DataFrame({"placeholder": [0]})
            else:
                df = pd.DataFrame({c: [0] for c in reversed(cols)})
            df.to_excel(xw, sheet_name=sheet, index=False)
    findings = structure_findings(path, cfg)
    assert not any("column mismatch" in f[2] for f in findings), findings


def test_structure_gate_still_flags_missing_column(tmp_path):
    from syngen.linter import expected_sheets_for, structure_findings
    cfg = base_cfg()
    expected = expected_sheets_for(cfg)
    # drop one real column from the opportunities contract
    opp = [c for c in expected["opportunities"] if c != "account_id"]
    expected["opportunities"] = opp
    path = tmp_path / "wb.xlsx"
    with pd.ExcelWriter(path) as xw:
        for sheet, cols in expected.items():
            df = (pd.DataFrame({c: [0] for c in cols}) if cols
                  else pd.DataFrame({"placeholder": [0]}))
            df.to_excel(xw, sheet_name=sheet, index=False)
    findings = structure_findings(path, cfg)
    assert any("column mismatch" in f[2] and "account_id" in f[2]
               for f in findings), findings


# --- S22.1 NaN coordinate is structural -------------------------------------


def test_quota_vs_potential_missing_unit_is_structural():
    opp = pd.DataFrame({"x": [1]})
    accounts = pd.DataFrame({"region": ["A", "A", "B"],
                             "market_potential_usd": [1e6, 2e6, 3e6]})
    plan = pd.DataFrame({"plan_unit": ["A", "C"],
                         "target_realized_usd": [1e6, 1e6]})
    params = {"_quota_df": plan, "dimension": "region",
              "target_ratio_pct": 100, "band_pp": 10}
    r = check_quota_vs_potential(opp, accounts, params)
    assert r.get("structural") is True


def test_quota_vs_potential_all_units_present_is_not_structural():
    opp = pd.DataFrame({"x": [1]})
    accounts = pd.DataFrame({"region": ["A", "A", "B"],
                             "market_potential_usd": [1e6, 2e6, 3e6]})
    plan = pd.DataFrame({"plan_unit": ["A", "B"],
                         "target_realized_usd": [1e6, 3e6]})
    params = {"_quota_df": plan, "dimension": "region",
              "target_ratio_pct": 100, "band_pp": 10}
    r = check_quota_vs_potential(opp, accounts, params)
    assert not r.get("structural")


# --- solver discipline: explicit null params --------------------------------


def test_solver_tolerates_explicit_null_coverage_param():
    cfg = base_cfg()
    q = cfg["time_model"]["quarter_labels"][0]
    doc = {"criteria": [crit("AC1", "coverage_ratio", quarter=q,
                             min_multiple=3.5, target_quarter_offset=None)]}
    autocalibrate(cfg, doc)  # must not raise (cert s21 crash)


def test_solver_tolerates_explicit_null_concentration_params():
    cfg = _big_cfg()
    doc = {"criteria": [crit("AC4", "pipeline_concentration",
                             top_n_accounts=None, min_top_share_pct=None)]}
    autocalibrate(cfg, doc)  # defaults 5 / 50, must not raise
    sigma = float(cfg["opportunities"]["deal_size_lognormal"]["sigma"])
    assert 0.0 < sigma <= envelope.SIGMA_CAP
