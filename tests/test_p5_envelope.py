"""P5 flight-control envelope: regression tests per certification
failure family (findings_v2.md batches 1-10).

Each test replays a class of failure observed live and asserts the new
deterministic gate catches it at the right layer - permanently, for any
similar scenario, not just the story that exposed it.
"""
import json

import pytest

from syngen.config import ConfigError, validate_simulator_doc
from syngen.generator.engine import generate_to_workbook
from syngen.phases.converge import _remedy_quota_potential
from syngen.phases.criteria_lint import (cross_lint, lint_criteria_internal,
                                         unit_spaces)
from syngen.phases.preflight import autocalibrate

from test_entity_schemas import ALL_BLOCKS_CFG


def base_cfg(**drop):
    cfg = json.loads(json.dumps(ALL_BLOCKS_CFG))
    for k in drop:
        cfg.pop(k, None)
    return validate_simulator_doc(cfg)


def crit(cid, check, **params):
    return {"id": cid, "name": cid, "check": check,
            "params": params, "classification": "parametric",
            "source_claim": cid}


def llm_json(obj):
    from syngen.llm.client import LLMResponse
    return LLMResponse(content=json.dumps(obj))


# --- F15.2 / F18.2: conflicting targets through Gate 1 (WP2) ------------------


def test_conflicting_company_targets_are_unsatisfiable():
    doc = {"criteria": [
        crit("AC1", "revenue_vs_plan", segment="_all_", dimension="segment",
             target_pct=94, band_pct=2),
        crit("AC2", "revenue_vs_plan", segment="_all_", dimension="segment",
             target_pct=100, band_pct=2),
    ]}
    hard, _ = lint_criteria_internal(doc)
    assert any("jointly unsatisfiable" in h for h in hard)


def test_overlapping_targets_are_allowed():
    doc = {"criteria": [
        crit("AC1", "revenue_vs_plan", segment="_all_", dimension="segment",
             target_pct=99, band_pct=2),
        crit("AC2", "revenue_vs_plan", segment="_all_", dimension="segment",
             target_pct=100, band_pct=2),
    ]}
    hard, _ = lint_criteria_internal(doc)
    assert not any("unsatisfiable" in h for h in hard)


def test_same_check_different_coordinates_do_not_conflict():
    doc = {"criteria": [
        crit("AC4", "quota_vs_potential", dimension="segment",
             unit="Enterprise", target_ratio_pct=120, band_pp=10),
        crit("AC5", "quota_vs_potential", dimension="segment",
             unit="Mid-Market", target_ratio_pct=40, band_pp=10),
    ]}
    hard, _ = lint_criteria_internal(doc)
    assert not hard


# --- F11.x / F18.3: foreign coordinates (WP3 cross-lint) ----------------------


def test_pseudo_unit_from_story_nouns_is_rejected():
    cfg = base_cfg()
    doc = {"criteria": [
        crit("AC3", "effective_capacity", target_pct=110, band_pp=5,
             unit="headline")]}
    findings = cross_lint(cfg, doc)
    assert any("'headline'" in f and "outside the data model" in f
               for f in findings)


def test_segment_unit_against_territory_capacity_is_rejected():
    cfg = base_cfg()
    doc = {"criteria": [
        crit("AC8", "effective_capacity", target_pct=82, band_pp=8,
             unit="Enterprise")]}
    findings = cross_lint(cfg, doc)
    assert any("'Enterprise'" in f and "capacity_units" in f
               for f in findings)


def test_legal_units_pass_cross_lint():
    cfg = base_cfg()
    doc = {"criteria": [
        crit("AC8", "effective_capacity", target_pct=82, band_pp=8,
             unit="AMER-East"),
        crit("AC7", "avg_discount_quarter", quarter="FY26-Q3",
             target_pct=16, tolerance_pp=2),
        crit("AC9", "tier_share_shift", tier="entry", from_share_pct=25,
             to_share_pct=40, tolerance_pp=5),
    ]}
    assert cross_lint(cfg, doc) == []


def test_multi_value_coordinate_regions_accepted():
    cfg = base_cfg()
    doc = {"criteria": [
        crit("AC5", "region_discount_premium", region="EMEA",
             vs=["AMER"], min_premium_pp=8)]}
    assert cross_lint(cfg, doc) == []


# --- F13.2: price caps unreachable under raking (WP6) --------------------------


def test_price_cap_below_raking_floor_is_flagged():
    cfg = base_cfg()
    cfg["quota"]["by_segment"] = {
        seg: [5_000_000.0] * 4 for seg in ["Enterprise", "Mid-Market", "SMB"]}
    doc = {"criteria": [
        crit("AC9", "avg_price_by_tier", tier="entry",
             max_avg_realized_usd=15000)]}
    findings = cross_lint(cfg, doc)
    assert any("economically unreachable under raking" in f
               for f in findings)


def test_reasonable_price_cap_is_not_flagged():
    cfg = base_cfg()
    doc = {"criteria": [
        crit("AC9", "avg_price_by_tier", tier="entry",
             max_avg_realized_usd=15000)]}
    assert not any("unreachable" in f for f in cross_lint(cfg, doc))


# --- F14.1: uniform required-block synthesis (WP4) ------------------------------


def test_capacity_block_synthesized_for_headcount_placement():
    cfg = base_cfg(capacity=None)
    doc = {"criteria": [
        crit("AC3", "headcount_growth_placement", min_growth_share_pct=60)]}
    fixes = autocalibrate(cfg, doc)
    assert "capacity" in cfg, "placement criterion must synthesize capacity"
    assert any("capacity" in f for f in fixes)


# --- F11.1 / F18.1: phantom solves impossible (WP4) ------------------------------


def test_capacity_solver_refuses_absent_unit_as_finding():
    cfg = base_cfg()
    doc = {"criteria": [
        crit("AC8", "effective_capacity", target_pct=82, band_pp=8,
             unit="Enterprise")]}
    with pytest.raises(ConfigError, match="'Enterprise' does not exist"):
        autocalibrate(cfg, doc)


# --- F15.1: scoped-first unit ledger (WP4) ----------------------------------------


def _remedy_fixture(tmp_path):
    cfg = base_cfg(products=None, pipeline=None, forecast=None,
                   ownership=None, activity=None, pricing_response=None,
                   capacity=None)
    cfg["opportunities"].pop("outlier_deals", None)
    cfg["accounts"].pop("territories", None)
    cfg["quota"] = {
        "by_segment": {"Enterprise": [300_000.0] * 4,
                       "SMB": [200_000.0] * 4},
        "attainment_by_segment": {"Enterprise": 0.95, "SMB": 1.04},
    }
    cfg["output"]["workbook"] = str(tmp_path / "ds.xlsx")
    _, wb = generate_to_workbook(validate_simulator_doc(cfg))

    doc = {"criteria": [
        crit("AC1", "quota_vs_potential", dimension="segment",
             unit="Enterprise", target_ratio_pct=120, band_pp=10),
        crit("AC2", "quota_vs_potential", dimension="segment",
             target_ratio_pct=40, band_pp=10),
    ]}
    results = [{"id": "AC1", "verdict": "FAIL"},
               {"id": "AC2", "verdict": "FAIL"}]

    class S:
        def log(self, *_a, **_k):
            pass

    return cfg, wb, doc, results, S()


def test_unscoped_criterion_never_clobbers_scoped_unit(tmp_path):
    cfg, wb, doc, results, sess = _remedy_fixture(tmp_path)
    before = json.loads(json.dumps(cfg["quota"]["by_segment"]))
    fixes = _remedy_quota_potential(cfg, doc, results, str(wb),
                                    lambda *_: None, sess)
    assert fixes, "remedy should scale plans"
    import pandas as pd
    acc = pd.read_excel(wb, sheet_name="accounts")

    def ratio(unit):
        pot = acc.loc[acc["segment"] == unit, "market_potential_usd"].sum()
        return sum(cfg["quota"]["by_segment"][unit]) / pot * 100

    ent, smb = ratio("Enterprise"), ratio("SMB")
    assert abs(ent - 120) <= 2, f"scoped unit must hit ITS OWN target: {ent}"
    assert abs(smb - 40) <= 2, f"unscoped claim solved on unpinned units: {smb}"
    # and the old bug would have left BOTH at 40 - prove Enterprise moved up
    assert cfg["quota"]["by_segment"]["Enterprise"] != before["Enterprise"]


# --- F12.1: input hardening (WP5) -------------------------------------------------


def test_list_valued_dimension_raises_configerror_not_attributeerror():
    cfg = base_cfg(capacity=None, products=None, pipeline=None, quota=None,
                   ownership=None, activity=None, forecast=None,
                   pricing_response=None)
    cfg["accounts"].pop("territories", None)
    cfg["opportunities"].pop("outlier_deals", None)
    cfg["accounts"]["regions"] = ["AMER", "EMEA"]
    with pytest.raises(ConfigError, match="must map names to weights"):
        validate_simulator_doc(cfg)


def test_list_valued_margin_map_raises_configerror():
    cfg = base_cfg()
    cfg["products"]["margin_by_tier"] = [0.55, 0.7, 0.8]
    with pytest.raises(ConfigError, match="margin_by_tier must map"):
        validate_simulator_doc(cfg)


# --- F16.1 / WP7: proposer knowledge injection ------------------------------------


def test_sign_conventions_reach_the_proposer_prompt():
    from syngen.phases.intake import _pack_taxonomy
    knowledge = _pack_taxonomy().check_knowledge()
    assert "creation_volume_trend.target_decline_pct" in knowledge
    assert "GROWTH" in knowledge
    assert "ATTAINMENT KNOBS CANNOT MOVE THIS RATIO" in knowledge


# --- WP9: critic wiring -------------------------------------------------------------

CRITIC_BLOCK = {"verdict": "issues", "issues": [
    {"id": "AC2", "severity": "block",
     "issue": "story says discounts DEEPENED; AC2 encodes a decline",
     "suggestion": "flip the trend direction"}]}


def test_pipeline_escalates_criteria_consistency_after_failed_redraft(
        tmp_path, monkeypatch):
    """F15.2/F18.2 end-to-end: provably conflicting company targets die at
    Gate 1 with a precise reason instead of after a doomed flight."""
    monkeypatch.chdir(tmp_path)
    from syngen.llm.client import FakeLLM
    from syngen.pipeline import run_new_story
    from test_pipeline import AUDIT_COVERED, PRECHECK, SilentIO

    conflicting = {"definitions": {}, "criteria": [
        crit("AC1", "revenue_vs_plan", segment="_all_", dimension="segment",
             target_pct=94, band_pct=2),
        crit("AC2", "revenue_vs_plan", segment="_all_", dimension="segment",
             target_pct=100, band_pct=2),
    ]}
    client = FakeLLM([
        llm_json(PRECHECK),
        llm_json(conflicting),   # draft 1 -> lint hard
        llm_json(AUDIT_COVERED),
        llm_json(conflicting),   # corrective re-draft: still conflicting
        llm_json(AUDIT_COVERED),
    ])
    result = run_new_story(client, "Revenue was flat.", SilentIO(),
                           sessions_dir="sessions", slug="consistency",
                           use_critic=False)
    assert result["status"] == "escalated"
    assert result["reason"] == "criteria_consistency"
    sdir = next((tmp_path / "sessions").iterdir())
    log_text = (sdir / "session_log.md").read_text(encoding="utf-8")
    assert "jointly unsatisfiable" in log_text


def test_critic_block_verdict_triggers_corrective_redraft(
        tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from syngen.llm.client import FakeLLM
    from syngen.pipeline import run_new_story
    from test_pipeline import (AUDIT_COVERED, BROKEN_SIM, PRECHECK,
                               SilentIO)

    # 'bad' passes the coverage guard but carries an off-story criterion
    # (a price cap on entry tier) that the CRITIC blocks; the corrected
    # draft drops it.
    base_crits = [
        {"id": "AC1", "name": "sanity", "check": "data_sanity",
         "params": {"max_discount_pct": 40},
         "classification": "parametric", "source_claim": "realism"},
        {"id": "AC2", "name": "discounts deepen",
         "check": "discount_trend_monotonic", "params": {"max_dip_pp": 3},
         "classification": "parametric", "source_claim": "creep"}]
    bad = {"definitions": {}, "criteria": base_crits + [
        {"id": "AC3", "name": "entry price cap",
         "check": "avg_price_by_tier",
         "params": {"tier": "entry", "max_avg_realized_usd": 15000},
         "classification": "parametric", "source_claim": "nothing"}]}
    good = {"definitions": {}, "criteria": base_crits}
    client = FakeLLM([
        llm_json(PRECHECK),
        llm_json(bad),
        llm_json(AUDIT_COVERED),
        llm_json(CRITIC_BLOCK),
        llm_json(good),
        llm_json(AUDIT_COVERED),
        llm_json({"verdict": "clean", "issues": []}),
        llm_json(BROKEN_SIM),
    ])
    result = run_new_story(client, "Discounts deepened.", SilentIO(),
                           sessions_dir="sessions", slug="criticA",
                           use_critic=True)
    sdir = next((tmp_path / "sessions").iterdir())
    log_text = (sdir / "session_log.md").read_text(encoding="utf-8")
    assert "CRITIC (criteria)" in log_text
    assert result["status"] != "error"


def test_critic_failure_fails_open(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from syngen.llm.client import FakeLLM
    from syngen.pipeline import run_new_story
    from test_pipeline import (BROKEN_SIM, CRITERIA, AUDIT_COVERED,
                               PRECHECK, SilentIO)

    def critic_killer(call):
        if "CRITIC" in call["system"][:100]:
            raise RuntimeError("critic endpoint gone")
        return llm_json({"verdict": "clean", "issues": []})

    client = FakeLLM([
        llm_json(PRECHECK),
        llm_json(CRITERIA),
        llm_json(AUDIT_COVERED),
        critic_killer,
        llm_json(BROKEN_SIM),
        critic_killer,
    ])
    result = run_new_story(client, "Q4 discounts deepened, worst in EMEA.",
                           SilentIO(), sessions_dir="sessions",
                           slug="criticdead", use_critic=True)
    # both critic passes crashed; the flight still completed on its own
    # deterministic machinery - fail-open verified end to end
    assert result["status"] == "converged"
