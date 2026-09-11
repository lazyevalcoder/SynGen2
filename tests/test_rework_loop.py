"""P7 flexible stage-rework loop: escalation evidence -> LLM judge ->
bounded re-dispatch back to criteria/config drafting.

Core guarantees under test:
- A judge routes escalation evidence to a claim-preserving criteria rework.
- The claim-preservation guard REJECTS a rework that drops coverage.
- A judge that fails (crash / malformed) fails OPEN to escalate, never loops.
- run_new_story keeps the rigid one-way behavior by default (rounds=0);
  run_fly enables the bounded rework budget.
"""
import json

import pytest

from syngen.llm.client import FakeLLM, LLMResponse
from syngen.pipeline import run_new_story
from syngen.phases import rework

from test_p5_envelope import base_cfg, crit
from test_pipeline import (AUDIT_COVERED, BROKEN_SIM, CRITERIA, PRECHECK,
                           SilentIO)
from test_coverage_guard import GENERIC_ONLY


def llm_json(obj):
    return LLMResponse(content=json.dumps(obj))


def _cfg_with_quota():
    cfg = base_cfg()
    cfg["quota"] = {
        "by_segment": {
            "Enterprise": [100000.0] * 4,
            "SMB": [40000.0] * 4,
        },
        "attainment_by_segment": {"Enterprise": 1.0, "SMB": 1.0},
    }
    return cfg


def _geometry_bad_criteria():
    return {"definitions": {}, "criteria": [
        crit("AC3", "quota_vs_potential", dimension="territory",
             unit="small_territories", target_ratio_pct=70, band_pp=10),
        crit("AC4", "data_sanity", max_discount_pct=40),
    ]}


def _judge_verdict(action, scope=None, guidance="", reason="test"):
    return {"action": action, "scope": scope or [],
            "guidance": guidance, "reason": reason}


# --- judge behavior --------------------------------------------------------


def test_judge_fails_open_on_crash():
    class Boom(FakeLLM):
        def chat(self, *a, **k):
            raise RuntimeError("endpoint gone")

    doc = {"criteria": [crit("AC1", "data_sanity", max_discount_pct=40)]}
    verdict = rework.judge_revision(Boom([]), "some story",
                                    {"kind": "convergence", "reason": "x",
                                     "criteria": []}, doc, 1)
    assert verdict["action"] == "escalate"


def test_judge_normalizes_invalid_action_to_escalate():
    client = FakeLLM([llm_json({"action": "launch_rocket", "scope": []})])
    doc = {"criteria": [crit("AC1", "data_sanity", max_discount_pct=40)]}
    verdict = rework.judge_revision(client, "story", {"kind": "convergence",
                                                      "reason": "x"}, doc, 1)
    assert verdict["action"] == "escalate"


def test_judge_rejects_scope_for_unknown_criteria():
    client = FakeLLM([llm_json(_judge_verdict("rework_criteria", ["AC99"]))])
    doc = {"criteria": [crit("AC1", "data_sanity", max_discount_pct=40)]}
    verdict = rework.judge_revision(client, "story", {"kind": "convergence",
                                                      "reason": "x"}, doc, 1)
    assert verdict["action"] == "rework_criteria"
    assert verdict["scope"] == []          # unknown ids filtered out


# --- claim-preservation guard ---------------------------------------------


def test_redraft_rejected_when_it_drops_coverage():
    client = FakeLLM([
        llm_json(GENERIC_ONLY),   # re-draft covers no computable claims
        llm_json(GENERIC_ONLY),   # corrective attempt still vacuous
    ])
    claims = {"claims": [{"claim": "quotas mismatch potential",
                          "classification": "COMPUTABLE"}]}
    doc = _geometry_bad_criteria()
    new_doc, ok = rework.redraft_criteria(
        client, "quotas mismatch", doc, claims, "",
        "re-express", log_fn=lambda *a, **k: None)
    assert ok is False
    assert new_doc is doc          # original doc untouched on rejection


# --- integration: a geometry death is re-routed and re-lands --------------

# Scripted FakeLLM flight with use_critic=False, max_rework_rounds=1:
#   attempt 0 drafts geometry-bad criteria -> geometry escalation (evidence)
#   judge orders rework_criteria -> claim-preserving GOOD re-draft
#   attempt 1 drafts the landing config and converges deterministically.
def test_convergence_escalation_is_routed_back_and_lands(tmp_path,
                                                         monkeypatch):
    monkeypatch.chdir(tmp_path)
    sim_q = _cfg_with_quota()
    client = FakeLLM([
        llm_json(PRECHECK),                      # 1  pre-check
        llm_json(_geometry_bad_criteria()),      # 2  initial draft (bad geo)
        llm_json(AUDIT_COVERED),                 # 3  coverage audit clean
        llm_json(sim_q),                         # 4  sim draft (attempt 0)
        llm_json(_geometry_bad_criteria()),      # 5  geo corrective re-draft
        llm_json(AUDIT_COVERED),                 # 6  coverage audit (re-draft)
        llm_json(_judge_verdict(                 # 7  rework judge -> criteria
            "rework_criteria", ["AC3"],
            "small_territories cannot be built; re-express the quota-vs-"
            "potential claim in an achievable form")),
        llm_json(CRITERIA),                      # 8  claim-preserving GOOD re-draft
        llm_json(AUDIT_COVERED),                 # 9  coverage audit clean
        llm_json(BROKEN_SIM),                    # 10 sim draft (attempt 1, lands)
    ])
    result = run_new_story(client, "Quotas mismatch potential.", SilentIO(),
                           sessions_dir="sessions", slug="rework",
                           use_critic=False, max_rework_rounds=1)
    assert result["status"] == "converged"
    assert result["rework"]["rounds"] == 1
    assert result["rework"]["directives"][0]["action"] == "rework_criteria"


# --- bound enforcement -----------------------------------------------------


def test_rework_judge_escalate_stops_without_retry(tmp_path, monkeypatch):
    """When the judge escalates, the flight ends with the judge's reason -
    no further delivery attempt runs."""
    monkeypatch.chdir(tmp_path)
    sim_q = _cfg_with_quota()
    client = FakeLLM([
        llm_json(PRECHECK),                      # 1
        llm_json(_geometry_bad_criteria()),      # 2
        llm_json(AUDIT_COVERED),                 # 3
        llm_json(sim_q),                         # 4
        llm_json(_geometry_bad_criteria()),      # 5
        llm_json(AUDIT_COVERED),                 # 6
        llm_json(_judge_verdict(                 # 7 judge -> escalate
            "escalate", [], "",
            reason="no revision credibly helps")),
    ])
    result = run_new_story(client, "Quotas mismatch potential.", SilentIO(),
                           sessions_dir="sessions", slug="reworkstop",
                           use_critic=False, max_rework_rounds=3)
    assert result["status"] == "escalated"
    assert result["reason"] == "criteria_geometry [judge: no revision credibly helps]"
    assert result["rework"]["rounds"] == 1


def test_rework_budget_exhausted_is_final(tmp_path, monkeypatch):
    """With rounds=0 (legacy one-way behavior) an escalation is terminal and
    carries rework metadata stating zero rounds were available."""
    monkeypatch.chdir(tmp_path)
    sim_q = _cfg_with_quota()
    client = FakeLLM([
        llm_json(PRECHECK),                      # 1
        llm_json(_geometry_bad_criteria()),      # 2
        llm_json(AUDIT_COVERED),                 # 3
        llm_json(sim_q),                         # 4
        llm_json(_geometry_bad_criteria()),      # 5
        llm_json(AUDIT_COVERED),                 # 6
    ])
    result = run_new_story(client, "Quotas mismatch potential.", SilentIO(),
                           sessions_dir="sessions", slug="rigid",
                           use_critic=False, max_rework_rounds=0)
    assert result["status"] == "escalated"
    assert result["reason"] == "criteria_geometry"
    assert result["rework"]["rounds"] == 0


# --- S10.2: structural config failures bypass the LLM judge ----------------


class _SilentSession:
    def log(self, *_a, **_k):
        pass


def _fake_attempt(kind, reason):
    def _attempt(*_a, **_k):
        evidence = {"kind": kind, "reason": reason, "detail": "PF0 config "
                    "invalid: headcount_actual must be non-negative integers",
                    "criteria": [], "margins": {}}
        return ({"status": "escalated", "reason": reason, "session": "s"},
                {"criteria": []}, evidence)
    return _attempt


def test_structural_preflight_failure_skips_judge(monkeypatch):
    """S10.2: a structural (config-invalid) escalation must NOT be handed to
    the LLM judge - the judge has no engine knowledge and misattributes it to
    a criteria ceiling. It escalates directly with the real cause."""
    from syngen import pipeline

    monkeypatch.setattr(pipeline, "_delivery_attempt",
                        _fake_attempt("preflight_structural",
                                      "preflight_structural"))

    class Boom(FakeLLM):
        def chat(self, *_a, **_k):
            raise AssertionError("judge must not run for structural failures")

    result = pipeline._delivery_rework(
        session=_SilentSession(), client=Boom([]), io=None, story="story",
        doc={"criteria": []}, claims={}, decisions_text="", spec_notes="",
        log=lambda *_a, **_k: None, max_iterations=10, max_llm_proposals=8,
        use_critic=False, max_rework_rounds=2)
    assert result["status"] == "escalated"
    assert result["reason"] == "preflight_structural"
    assert result["rework"]["rounds"] == 0
    assert result["rework"]["directives"] == []


def test_nonstructural_preflight_failure_still_judged(monkeypatch):
    """Complement to the above: a non-structural preflight failure (PF1 etc.)
    is still routed to the judge as before."""
    from syngen import pipeline

    monkeypatch.setattr(pipeline, "_delivery_attempt",
                        _fake_attempt("preflight_persist",
                                      "preflight_calibration"))
    client = FakeLLM([llm_json(_judge_verdict("escalate", [], "",
                                              reason="no revision helps"))])
    result = pipeline._delivery_rework(
        session=_SilentSession(), client=client, io=None, story="story",
        doc={"criteria": []}, claims={}, decisions_text="", spec_notes="",
        log=lambda *_a, **_k: None, max_iterations=10, max_llm_proposals=8,
        use_critic=False, max_rework_rounds=2)
    assert result["status"] == "escalated"
    assert result["reason"] == "preflight_calibration [judge: no revision helps]"
    assert result["rework"]["rounds"] == 1
