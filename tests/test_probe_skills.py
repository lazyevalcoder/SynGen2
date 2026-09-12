"""P10 step 1+2: token accounting, the skills toggle, and the criteria probe.

The probe stops before the tuning loop, so these tests are fast and assert the
deterministic outcomes (gate survival, usage totals, skills on/off).
"""
import json

from syngen.llm.client import FakeLLM, LLMClient, LLMResponse
from syngen.phases.intake import draft_criteria
from syngen.probe import probe_criteria

from test_pipeline import (AUDIT_COVERED, BROKEN_SIM, CRITERIA, PRECHECK)


def llm_json(obj):
    return LLMResponse(content=json.dumps(obj))


# --- step 1: token accounting ------------------------------------------------


def test_client_accumulates_usage_across_calls(monkeypatch):
    client = LLMClient(config={"max_attempts": 1})

    def fake_call(system, user, max_tokens, temperature, attempt, effort,
                  enable_thinking=None, reasoning_budget_tokens=None):
        return LLMResponse(content="{}", usage={
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})

    monkeypatch.setattr(client, "_call", fake_call)
    client.chat("s", "u")
    client.chat("s", "u")
    totals = client.usage_totals()
    assert totals["calls"] == 2
    assert totals["prompt_tokens"] == 20
    assert totals["completion_tokens"] == 10
    assert totals["total_tokens"] == 30


def test_usage_totals_defaults_to_zero():
    assert LLMClient().usage_totals()["total_tokens"] == 0


# --- step 2: skills toggle ---------------------------------------------------


def test_draft_criteria_skills_toggle_changes_prompt():
    """use_skills now injects the numeric CAPABILITY SHEET (the rulebook was
    replaced): present when on, absent when off."""
    for use_skills, expected in ((True, True), (False, False)):
        client = FakeLLM([llm_json(CRITERIA)])
        draft_criteria(client, "story", "", use_skills=use_skills)
        system = client.calls[-1]["system"]
        assert ("CAPABILITY SHEET" in system) is expected


# --- step 2: criteria probe --------------------------------------------------


def test_probe_gate1_pass_and_usage_calls():
    client = FakeLLM([
        llm_json(PRECHECK),        # precheck
        llm_json(CRITERIA),        # draft criteria
        llm_json(AUDIT_COVERED),   # coverage audit
        llm_json({"issues": []}),  # critic verdict (clean)
    ])
    res = probe_criteria(client, "story", use_skills=True, use_critic=True)
    assert res["gate1_pass"] is True
    assert res["coverage"] != "uncovered"
    assert res["llm_usage"]["calls"] == 4


def test_probe_with_config_reports_reachability():
    client = FakeLLM([
        llm_json(PRECHECK),
        llm_json(CRITERIA),
        llm_json(AUDIT_COVERED),
        llm_json({"issues": []}),  # critic (criteria)
        llm_json(BROKEN_SIM),      # simulator draft
    ])
    res = probe_criteria(client, "story", use_skills=True, use_critic=True,
                         with_config=True)
    assert "reachable_pass" in res
    assert "geometry_findings" in res
    assert res["llm_usage"]["calls"] == 5
