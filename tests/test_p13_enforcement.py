"""P13 enforcement: menu walls, stage-3 buildability, reachable ranges."""
import json

import pytest

from syngen.llm.client import FakeLLM, LLMResponse

from test_p5_envelope import crit
from test_pipeline import BROKEN_SIM


def _resp(obj):
    return LLMResponse(content=json.dumps(obj))


CORE = {"accounts": BROKEN_SIM["accounts"],
        "opportunities": BROKEN_SIM["opportunities"]}


# --- menu as a wall ---------------------------------------------------------

def test_buildable_list_and_catalog_exclude_blocked():
    from syngen.menu import buildable_catalog, buildable_check_names
    names = buildable_check_names()
    assert "quota_vs_potential" not in names
    assert "win_rate_flat" in names
    catalog = buildable_catalog()
    assert "quota_vs_potential" not in catalog
    assert "win_rate_flat" in catalog


def test_menu_findings_flags_blocked_unknown_and_duplicate():
    from syngen.menu import menu_findings
    doc = {"criteria": [
        crit("AC1", "quota_vs_potential", target_ratio_pct=120, band_pp=5),
        crit("AC2", "not_a_real_check"),
        crit("AC3", "win_rate_flat", band_pp=5),
        crit("AC4", "win_rate_flat", band_pp=5),
    ]}
    # make AC3/AC4 exact duplicates (same source_claim)
    doc["criteria"][2]["source_claim"] = "same"
    doc["criteria"][3]["source_claim"] = "same"
    findings = menu_findings(doc)
    assert any("AC1" in f and "BLOCKED" in f for f in findings)
    assert any("AC2" in f and "not a registered" in f for f in findings)
    assert any("AC4" in f and "duplicate" in f for f in findings)


def test_engine_limits_reports_pinned_and_blocked():
    from syngen.menu import engine_limits_for
    text = engine_limits_for(["revenue_vs_plan", "quota_vs_potential"])
    assert "raking pins" in text
    assert "BLOCKED" in text


def test_coverage_audit_prompt_never_offers_blocked_checks():
    from syngen.phases.intake import _pack_taxonomy
    from syngen.menu import blocked_checks, buildable_check_names
    from syngen.prompts import load_prompt
    allowed = buildable_check_names()
    blocked = blocked_checks()
    assert blocked  # sanity
    text = load_prompt("coverage_audit", checks=allowed)
    for b in blocked:
        assert b not in text


# --- stage-3 buildability ---------------------------------------------------

def test_verify_config_flags_missing_block_and_feature():
    from syngen.phases.buildability import verify_config
    cfg = {"accounts": {"count": 100}, "opportunities": {"per_quarter": 10}}
    findings = verify_config(cfg, ["elasticity_differential"])
    assert any("pricing_response" in f for f in findings)
    assert any("accounts.market_potential_usd" in f for f in findings)


def test_verify_config_passes_when_present():
    from syngen.phases.buildability import verify_config
    cfg = {"accounts": {"count": 100, "market_potential_usd": {"min": 1, "max": 2}},
           "opportunities": {"per_quarter": 10},
           "pricing_response": {"elasticity": -1.5}}
    assert verify_config(cfg, ["elasticity_differential"]) == []


def test_split_simulator_fails_honestly_when_block_stays_empty():
    from syngen.phases.buildability import BuildabilityError
    from syngen.phases.stage3 import split_simulator
    # core, empty pricing_response, repaired core, still-empty pricing_response
    client = FakeLLM([_resp(CORE), _resp({}), _resp(CORE), _resp({})])
    with pytest.raises(BuildabilityError, match="pricing_response"):
        split_simulator(client, "story", "criteria",
                        ["elasticity_differential"])


# --- reachable ranges -------------------------------------------------------

def _wr_cfg():
    return {"time_model": {"quarter_labels": ["Q1", "Q2", "Q3", "Q4"]},
            "accounts": {"count": 100},
            "opportunities": {"per_quarter": 600, "win_rate": 0.3,
                              "volume_multipliers": [1.0, 1.0, 1.0, 1.0]}}


def test_win_rate_noise_floor_value():
    from syngen.packs.revops.envelope import win_rate_noise_pp
    floor = win_rate_noise_pp(_wr_cfg())
    assert floor is not None and 3.0 < floor < 4.5


def test_cross_lint_flags_win_rate_band_below_noise():
    from syngen.phases.criteria_lint import cross_lint
    doc = {"criteria": [crit("AC1", "win_rate_flat", band_pp=3)]}
    findings = cross_lint(_wr_cfg(), doc, feasibility=True)
    assert any("win_rate_flat" in f and "noise floor" in f for f in findings)


def test_cross_lint_accepts_wide_win_rate_band():
    from syngen.phases.criteria_lint import cross_lint
    doc = {"criteria": [crit("AC1", "win_rate_flat", band_pp=10)]}
    findings = cross_lint(_wr_cfg(), doc, feasibility=True)
    assert not any("noise floor" in f for f in findings)


def test_capability_flags_narrow_win_rate_band():
    from syngen.capability import assess_criteria
    doc = {"criteria": [crit("AC1", "win_rate_flat", band_pp=3)]}
    f = assess_criteria(doc, _wr_cfg())[0]
    assert f["reachable"] is False
    assert f["nearest"] >= 3.0


def test_capability_notes_elasticity_needs_pricing_response():
    from syngen.capability import assess_criteria
    doc = {"criteria": [crit("AC1", "elasticity_differential", min_gap_pp=15)]}
    f = assess_criteria(doc)[0]
    assert "pricing_response" in f["note"]


# --- P16 cross-block unit consistency --------------------------------------

def test_cross_block_flags_quota_territory_mismatch():
    from syngen.phases.buildability import cross_block_findings
    cfg = {"accounts": {"territories": {"AMER-East": ["AMER"],
                                        "EMEA-North": ["EMEA"]}},
           "quota": {"by_territory": {"APAC-Commercial": [1, 2, 3, 4]}}}
    findings = cross_block_findings(cfg)
    assert any("quota" in f and "APAC-Commercial" in f for f in findings)


def test_cross_block_ok_when_units_match():
    from syngen.phases.buildability import cross_block_findings
    cfg = {"accounts": {"territories": {"AMER-East": ["AMER"]}},
           "quota": {"by_territory": {"AMER-East": [1, 2, 3, 4]}}}
    assert cross_block_findings(cfg) == []


def test_cross_block_flags_capacity_region_mismatch():
    from syngen.phases.buildability import cross_block_findings
    cfg = {"accounts": {"regions": {"AMER": 0.5, "EMEA": 0.5}},
           "capacity": {"by_region": {"LATAM": {"headcount_plan": [1, 1, 1, 1]}}}}
    findings = cross_block_findings(cfg)
    assert any("capacity" in f and "LATAM" in f for f in findings)


def test_split_simulator_repairs_quota_units_with_core_names():
    """P16: the quota block invents territory names; the gate re-drafts it
    with the core's real names and the assembly then validates."""
    from syngen.phases.stage3 import split_simulator
    core = {"accounts": {"count": 100,
                         "regions": {"AMER": 1.0},
                         "segments": {"Enterprise": 1.0},
                         "industries": ["Software"],
                         "territories": {"AMER-East": ["AMER"],
                                         "AMER-West": ["AMER"]}},
            "opportunities": BROKEN_SIM["opportunities"]}
    bad_quota = {"quota": {"by_territory": {"APAC-Commercial": [1, 2, 3, 4]}}}
    good_quota = {"quota": {"by_territory": {"AMER-East": [1, 2, 3, 4],
                                             "AMER-West": [1, 2, 3, 4]}}}
    # core, bad quota, (repair) good quota
    client = FakeLLM([_resp(core), _resp(bad_quota), _resp(good_quota)])
    cfg = split_simulator(client, "story", "criteria", ["revenue_vs_plan"])
    assert set(cfg["quota"]["by_territory"]) == {"AMER-East", "AMER-West"}


def test_map_effort_maps_medium_to_high():
    from syngen.llm.client import _map_effort
    assert _map_effort("minimal") == "low"
    assert _map_effort("medium") == "high"
    assert _map_effort("high") == "high"
    assert _map_effort("max") == "max"
    assert _map_effort(None) == "high"


# --- P17 fixes --------------------------------------------------------------

def test_blocked_check_has_a_buildable_replacement():
    from syngen.menu import replacement_for
    assert replacement_for("quota_vs_potential") == "potential_coverage_gap"
    assert replacement_for("win_rate_flat") is None


def test_menu_findings_flags_narrative_pseudo_unit():
    from syngen.menu import menu_findings
    doc = {"criteria": [{
        "id": "AC1", "name": "x", "check": "region_discount_premium",
        "params": {"region": "high-potential territory",
                   "vs": ["low-potential territory"],
                   "min_premium_pp": 5},
        "source_claim": "c"}]}
    findings = menu_findings(doc)
    assert any("narrative label" in f for f in findings)


def test_audit_item_maps_blocked_to_replacement():
    from syngen.phases.intake import _normalize_audit_item
    from syngen.validator.checks import CHECKS
    item = {"claim": "quota over market", "classification": "PARAMETRIC",
            "existing_check": "quota_vs_potential", "reason": "uncovered"}
    out = _normalize_audit_item(item, set(CHECKS))
    assert out["classification"] == "PARAMETRIC"
    assert out["check"] == "potential_coverage_gap"


def test_audit_item_degrades_when_no_replacement():
    from syngen.phases.intake import _normalize_audit_item
    from syngen.validator.checks import CHECKS
    item = {"claim": "x", "classification": "PARAMETRIC",
            "existing_check": "no_such_check", "reason": "uncovered"}
    out = _normalize_audit_item(item, set(CHECKS))
    assert out["classification"] == "VOCAB_GAP"
    assert out["check"] is None


def test_cross_block_flags_quota_attainment_dimension_mismatch():
    from syngen.phases.buildability import cross_block_findings
    cfg = {"accounts": {"territories": {"AMER-East": ["AMER"]}},
           "quota": {"by_territory": {"AMER-East": [1, 2, 3, 4]},
                     "attainment_by_segment": {"Enterprise": 0.95}}}
    findings = cross_block_findings(cfg)
    assert any("attainment" in f and "Enterprise" in f for f in findings)


def test_apply_changes_rejects_invented_key():
    from syngen.phases.converge import _apply_changes
    cfg = {"accounts": {"market_potential_usd": {"min": 1, "max": 2}},
           "opportunities": {}, "time_model": {"quarter_labels": ["Q"]},
           "output": {}, "seed": 1}
    applied = _apply_changes(cfg, [{
        "path": "accounts.market_potential_usd.high_pot_min", "to": 5}])
    assert any("error" in a for a in applied)
    assert "high_pot_min" not in cfg["accounts"]["market_potential_usd"]


def test_non_tunable_checks_set_covers_known_levers():
    from syngen.phases.converge import _NON_TUNABLE_CHECKS
    assert "elasticity_differential" in _NON_TUNABLE_CHECKS
    assert "post_change_revenue_decline" in _NON_TUNABLE_CHECKS


def test_dedupe_drops_same_claim_reexpression():
    from syngen.phases.stage2 import _dedupe
    doc = {"criteria": [
        {"id": "AC1", "check": "win_rate_flat", "params": {"band_pp": 5},
         "source_claim": "same"},
        {"id": "AC2", "check": "win_rate_flat", "params": {"band_pp": 8},
         "source_claim": "same"},
        {"id": "AC3", "check": "win_rate_flat", "params": {"band_pp": 8},
         "source_claim": "other"},
    ]}
    out = _dedupe(doc, lambda *a, **k: None)
    assert [c["id"] for c in out["criteria"]] == ["AC1", "AC3"]
