"""Coverage guard (M5 iter 5 item 0, retro R6): vacuous convergence hole.

#24 once "landed" with zero criteria; #9/#13 landed on generic hygiene
checks alone. The guard must catch both shapes deterministically and use
one LLM audit for the subtle cases, with exactly one corrective re-draft.
"""
import json

import pytest

from syngen.llm.client import FakeLLM, LLMResponse
from syngen.phases.intake import (
    audit_coverage,
    coherence_gaps,
    deterministic_gaps,
    enforce_coverage,
)

CLAIMS = {"claims": [
    {"claim": "unowned accounts ballooned in H2", "classification": "COMPUTABLE"},
    {"claim": "changed-owner revenue collapsed", "classification": "COMPUTABLE"},
    {"claim": "morale suffered", "classification": "NON_COMPUTABLE"},
]}

GENERIC_ONLY = {
    "definitions": {},
    "criteria": [
        {"id": "AC1", "name": "sanity", "check": "data_sanity",
         "params": {"max_discount_pct": 70}, "source_claim": "realism"},
    ],
}

REAL_CRITERIA = {
    "definitions": {},
    "criteria": [
        {"id": "AC1", "name": "sanity", "check": "data_sanity",
         "params": {}, "source_claim": "realism"},
        {"id": "AC2", "name": "unowned share", "check": "unowned_account_share",
         "params": {"min_share_pct": 20}, "source_claim": "unowned accounts"},
        {"id": "AC3", "name": "post-change decline",
         "check": "post_change_revenue_decline",
         "params": {"max_stable_growth_pct": 5},
         "source_claim": "changed-owner revenue"},
    ],
}


def llm_json(obj):
    return LLMResponse(content=json.dumps(obj))


def test_zero_criteria_is_a_gap():
    gaps = deterministic_gaps({"criteria": []}, ["some claim"])
    assert gaps and "No criteria" in gaps[0]


def test_generic_only_criteria_gap_names_the_claims():
    gaps = deterministic_gaps(GENERIC_ONLY, ["claim A", "claim B"])
    assert len(gaps) == 1
    assert "claim A" in gaps[0] and "data_sanity" in gaps[0]


def test_real_criteria_pass_deterministic_rules():
    assert deterministic_gaps(REAL_CRITERIA, ["x"]) == []


def test_no_computable_claims_means_no_generic_gap():
    # a pure-narrative story legitimately carries hygiene checks only
    assert deterministic_gaps(GENERIC_ONLY, []) == []


def test_audit_coverage_reports_uncovered():
    client = FakeLLM([llm_json({"uncovered": [
        {"claim": "changed-owner revenue collapsed",
         "reason": "no criterion measures owner-change cohorts",
         "suggested_check": "post_change_revenue_decline"}],
        "covered": ["unowned accounts"]})])
    gaps = audit_coverage(client, "story text", GENERIC_ONLY,
                          ["unowned accounts", "changed-owner revenue "
                           "collapsed"], log_fn=lambda *_: None)
    assert len(gaps) == 1
    assert "changed-owner" in gaps[0]
    assert "post_change_revenue_decline" in gaps[0]


def test_audit_fails_open_on_unparsable_output():
    # FakeLLM returns empty content when the script is exhausted ->
    # chat_json raises -> guard degrades to deterministic rules
    client = FakeLLM([])
    gaps = audit_coverage(client, "story", REAL_CRITERIA, ["a claim"],
                          log_fn=lambda *_: None)
    assert gaps == []


def test_enforce_redrafts_once_and_passes():
    # generic-only doc -> deterministic gap fires immediately (no audit
    # call); corrective re-draft -> re-audit covers
    client = FakeLLM([
        llm_json(REAL_CRITERIA),   # corrective re-draft
        llm_json({"uncovered": [], "covered": ["both"]}),  # re-audit
    ])
    doc, status = enforce_coverage(client, "story", GENERIC_ONLY, CLAIMS,
                                   log_fn=lambda *_: None)
    assert status == "redrafted"
    assert {c["check"] for c in doc["criteria"]} >= {
        "unowned_account_share"}


def test_enforce_escalates_when_gaps_persist():
    # plausible-looking criteria that pass the deterministic rules but
    # express none of the claims (the live #9/#13 shape)
    off_target = {"definitions": {}, "criteria": [
        {"id": "AC1", "name": "win rate", "check": "win_rate_flat",
         "params": {"band_pp": 10}, "source_claim": "narrative"},
        {"id": "AC2", "name": "sanity", "check": "data_sanity",
         "params": {}, "source_claim": "realism"},
    ]}
    uncovered = llm_json({"uncovered": [{"claim": "c", "reason": "r"}],
                          "covered": []})
    client = FakeLLM([
        uncovered,                 # initial audit: uncovered
        llm_json(off_target),      # corrective re-draft misses again
        uncovered,                 # re-audit still fails
    ])
    doc, status = enforce_coverage(client, "story", off_target, CLAIMS,
                                   log_fn=lambda *_: None)
    assert status == "uncovered"


def test_deterministic_gap_skips_the_initial_audit_call():
    # generic-only + computable claims: the gap is resolved by the cheap
    # rule - the first LLM traffic is the corrective re-draft itself,
    # followed by one re-audit; no audit ran before the redraft
    client = FakeLLM([
        llm_json(REAL_CRITERIA),
        llm_json({"uncovered": [], "covered": ["both"]}),
    ])
    doc, status = enforce_coverage(client, "story", GENERIC_ONLY, CLAIMS,
                                   log_fn=lambda *_: None)
    assert status == "redrafted"
    assert len(client.calls) == 2


def test_pipeline_escalates_on_vacuous_criteria(tmp_path, monkeypatch):
    """End-to-end R6 regression: #24's 0/0 / generic-only landings must
    now escalate as criteria_coverage instead of shipping."""
    monkeypatch.chdir(tmp_path)
    from test_pipeline import PRECHECK, SilentIO
    from syngen.pipeline import run_new_story

    uncovered = llm_json({"uncovered": [
        {"claim": "unowned accounts ballooned in H2",
         "reason": "hygiene only"}], "covered": []})
    off_target = {"definitions": {}, "criteria": [
        {"id": "AC1", "name": "win rate", "check": "win_rate_flat",
         "params": {"band_pp": 10}, "source_claim": "narrative"}]}
    client = FakeLLM([
        llm_json(PRECHECK),
        llm_json(GENERIC_ONLY),   # initial draft: hygiene only -> det. gap
        llm_json(off_target),     # corrective re-draft: plausible but off
        uncovered,                # audit still rejects -> escalate
    ])
    result = run_new_story(client, "Unowned accounts ballooned in H2.",
                           SilentIO(), sessions_dir="sessions", slug="cov")
    assert result["status"] == "escalated"
    assert result["reason"] == "criteria_coverage"


def test_coherence_company_attainment_outside_unit_range():
    doc = {"criteria": [
        {"id": "AC1", "check": "revenue_vs_plan",
         "params": {"segment": "Enterprise", "target_pct": 88, "band_pct": 2}},
        {"id": "AC2", "check": "revenue_vs_plan",
         "params": {"segment": "SMB", "target_pct": 96, "band_pct": 2}},
        {"id": "AC3", "check": "revenue_vs_plan",
         "params": {"segment": "_all_", "target_pct": 110, "band_pct": 2}},
    ]}
    gaps = coherence_gaps(doc)
    assert any("AC3" in g and "achievable range" in g for g in gaps)


def test_coherence_core_cannot_exceed_headline():
    # the live s25 shape: headline 101 while core demands more than that
    doc = {"criteria": [
        {"id": "AC1", "check": "revenue_vs_plan",
         "params": {"segment": "_all_", "target_pct": 101, "band_pct": 1}},
        {"id": "AC2", "check": "revenue_vs_plan",
         "params": {"segment": "_all_", "target_pct": 104,
                    "band_pct": 2, "exclude_outlier_deals": True}},
    ]}
    gaps = coherence_gaps(doc)
    assert any("core" in g for g in gaps)


def test_coherence_discount_vs_realized_contradiction():
    doc = {"criteria": [
        {"id": "AC1", "check": "avg_discount_quarter",
         "params": {"quarter": "FY26-Q4", "target_pct": 25, "tolerance_pp": 2}},
        {"id": "AC2", "check": "realized_vs_list",
         "params": {"quarter_start": "FY26-Q1", "target_start_pct": 90,
                    "quarter_end": "FY26-Q4", "target_end_pct": 84,
                    "tolerance_pp": 3}},
    ]}
    gaps = coherence_gaps(doc)
    assert any("contradict" in g for g in gaps)


def test_coherent_set_passes():
    doc = {"criteria": [
        {"id": "AC1", "check": "avg_discount_quarter",
         "params": {"quarter": "FY26-Q4", "target_pct": 16, "tolerance_pp": 2}},
        {"id": "AC2", "check": "realized_vs_list",
         "params": {"quarter_start": "FY26-Q1", "target_start_pct": 90,
                    "quarter_end": "FY26-Q4", "target_end_pct": 84,
                    "tolerance_pp": 3}},
        {"id": "AC3", "check": "revenue_vs_plan",
         "params": {"segment": "SMB", "target_pct": 95, "band_pct": 2}},
        {"id": "AC4", "check": "revenue_vs_plan",
         "params": {"segment": "_all_", "target_pct": 101, "band_pct": 2}},
    ]}
    assert coherence_gaps(doc) == []
