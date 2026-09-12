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
