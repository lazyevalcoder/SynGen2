"""Defect-Response rework: work order, runbook, fixer patch, verification.

Framework: triage -> runbook (deterministic) -> fixer (minimal-context LLM)
-> verify (guards). These tests cover each stage offline.
"""
import json

from syngen.llm.client import FakeLLM, LLMResponse
from syngen.phases import defect_response as dr

from test_p5_envelope import crit


def _doc(*crits):
    return {"definitions": {}, "criteria": list(crits)}


def _with_claim(c, claim):
    c = dict(c)
    c["source_claim"] = claim
    return c


def test_classify_blocked_path():
    v = {"action": "rework_criteria", "scope": ["AC3"], "reason": "",
         "guidance": "quota_vs_potential is a blocked path"}
    assert dr.classify_defect(v, {"kind": "convergence", "reason": ""}) \
        == "blocked_path"


def test_classify_one_sided():
    v = {"action": "rework_criteria", "scope": ["AC1"], "guidance": "",
         "reason": "one-sided bound can pass by overshooting"}
    assert dr.classify_defect(v, {"kind": "convergence", "reason": ""}) \
        == "one_sided"


def test_classify_draft_invalid_key_mismatch():
    v = {"action": "rework_config", "scope": [], "reason": "key mismatch",
         "guidance": ""}
    assert dr.classify_defect(
        v, {"kind": "draft_invalid",
            "reason": "not a known account motion"}) == "schema_key_mismatch"


def test_runbook_adds_ceiling_to_one_sided_coverage():
    doc = _doc(crit("AC1", "coverage_ratio", quarter="FY26-Q2",
                    min_multiple=3.5))
    patch = dr.runbook_fix({"defect_class": "one_sided", "targets": ["AC1"]},
                           doc)
    assert patch and patch[0]["params"]["max_multiple"] == 5.25


def test_runbook_adds_ceiling_to_concentration():
    doc = _doc(crit("AC3", "pipeline_concentration", top_n_accounts=5,
                    min_top_share_pct=50))
    patch = dr.runbook_fix({"defect_class": "one_sided", "targets": ["AC3"]},
                           doc)
    assert patch[0]["params"]["max_top_share_pct"] == 70.0


def test_runbook_skips_when_ceiling_present_or_unknown():
    bounded = _doc(crit("AC1", "coverage_ratio", quarter="FY26-Q2",
                        min_multiple=3.5, max_multiple=5))
    assert dr.runbook_fix({"defect_class": "one_sided",
                           "targets": ["AC1"]}, bounded) is None
    other = _doc(crit("AC1", "data_sanity", max_discount_pct=40))
    assert dr.runbook_fix({"defect_class": "one_sided",
                           "targets": ["AC1"]}, other) is None


def test_build_work_order_includes_only_relevant_check_facts():
    doc = _doc(crit("AC3", "quota_vs_potential", target_ratio_pct=120,
                    band_pp=5))
    v = {"action": "rework_criteria", "scope": ["AC3"], "reason": "blocked",
         "guidance": "re-express"}
    order = dr.build_work_order(v, {"kind": "convergence", "reason": ""}, doc)
    assert order["targets"] == ["AC3"]
    assert order["defect_class"] == "blocked_path"
    assert "blocked path" in order["allowed"].lower()


def test_verify_patch_rejects_source_claim_change():
    doc = _doc(_with_claim(crit("AC1", "coverage_ratio", quarter="FY26-Q2",
                                min_multiple=3.5), "coverage healthy"))
    patch = [{"id": "AC1", "check": "coverage_ratio",
              "params": {"quarter": "FY26-Q2", "min_multiple": 3.5,
                         "max_multiple": 5},
              "source_claim": "TAMPERED"}]
    _, ok, why = dr.verify_patch(patch, doc, {"AC1"})
    assert not ok and "source_claim" in why


def test_verify_patch_rejects_non_target():
    doc = _doc(crit("AC1", "coverage_ratio", quarter="FY26-Q2",
                    min_multiple=3.5))
    patch = [{"id": "AC9", "check": "coverage_ratio", "params": {},
              "source_claim": "AC9"}]
    _, ok, why = dr.verify_patch(patch, doc, {"AC1"})
    assert not ok and "non-target" in why


def test_verify_patch_accepts_valid_range():
    doc = _doc(_with_claim(crit("AC1", "coverage_ratio", quarter="FY26-Q2",
                                min_multiple=3.5), "coverage healthy"))
    patch = [{"id": "AC1", "check": "coverage_ratio",
              "params": {"quarter": "FY26-Q2", "min_multiple": 3.5,
                         "max_multiple": 5},
              "source_claim": "coverage healthy"}]
    new_doc, ok, why = dr.verify_patch(patch, doc, {"AC1"})
    assert ok, why
    assert new_doc["criteria"][0]["params"]["max_multiple"] == 5


def test_defect_response_uses_runbook_without_llm():
    doc = _doc(_with_claim(crit("AC1", "coverage_ratio", quarter="FY26-Q2",
                                min_multiple=3.5), "coverage healthy"))
    v = {"action": "rework_criteria", "scope": ["AC1"],
         "reason": "one-sided bound", "guidance": ""}
    new_doc, ok, directive = dr.defect_response(
        FakeLLM([]), v, {"kind": "convergence", "reason": "one-sided"}, doc)
    assert ok and directive["resolver"] == "runbook"
    assert new_doc["criteria"][0]["params"]["max_multiple"] == 5.25


def test_defect_response_fixer_path_produces_patch():
    doc = _doc(_with_claim(crit("AC3", "quota_vs_potential",
                                target_ratio_pct=120, band_pp=5),
                           "quotas set above potential"))
    patch = {"patch": [{
        "id": "AC3", "name": "core missed plan",
        "check": "revenue_vs_plan",
        "params": {"segment": "_all_", "exclude_outlier_deals": True,
                   "target_pct": 95, "band_pct": 3},
        "classification": "parametric",
        "source_claim": "quotas set above potential", "depends_on": []}],
        "rationale": "blocked path -> reachable form"}
    client = FakeLLM([LLMResponse(content=json.dumps(patch))])
    v = {"action": "rework_criteria", "scope": ["AC3"],
         "reason": "quota_vs_potential is a blocked path",
         "guidance": "re-express as the reachable form"}
    new_doc, ok, directive = dr.defect_response(
        client, v, {"kind": "convergence", "reason": "blocked path"}, doc)
    assert ok, directive
    assert directive["resolver"] == "fixer"
    assert new_doc["criteria"][0]["check"] == "revenue_vs_plan"


def test_defect_response_skips_non_criteria_action():
    doc = _doc(crit("AC1", "data_sanity", max_discount_pct=40))
    v = {"action": "rework_config", "scope": [], "reason": "x",
         "guidance": ""}
    _, ok, directive = dr.defect_response(
        FakeLLM([]), v, {"kind": "draft_invalid", "reason": "x"}, doc)
    assert not ok and directive["resolver"] == "skip"
