"""P11 split stage 2: claim form -> params -> deterministic assembly."""
import json

from syngen.llm.client import FakeLLM, LLMResponse
from syngen.phases.stage2 import draft_criteria_split, select_claim_forms

CLAIMS = {"claims": [
    {"claim": "Q4 discounts deeper", "classification": "COMPUTABLE"},
    {"claim": "win rates flat", "classification": "COMPUTABLE"},
    {"claim": "reps motivated", "classification": "NOT_COMPUTABLE"},
]}

FORMS = {"forms": [
    {"claim": "Q4 discounts deeper", "check": "avg_discount_quarter"},
    {"claim": "win rates flat", "check": "win_rate_flat"},
]}

CRITERIA = {"criteria": [
    {"id": "AC1", "name": "discounts", "check": "avg_discount_quarter",
     "params": {"quarter": "FY26-Q1", "target_pct": 12, "tolerance_pp": 4},
     "classification": "parametric", "source_claim": "Q4 discounts deeper"},
    {"id": "AC2", "name": "win flat", "check": "win_rate_flat",
     "params": {"band_pp": 8}, "classification": "statistical",
     "source_claim": "win rates flat"},
], "ambiguities": []}


def _resp(obj):
    return LLMResponse(content=json.dumps(obj))


def test_select_claim_forms_uses_only_computable():
    client = FakeLLM([_resp(FORMS)])
    out = select_claim_forms(client, "story", CLAIMS)
    assert len(out["forms"]) == 2
    assert "reps motivated" not in client.calls[0]["user"]


def test_split_drafts_criteria():
    client = FakeLLM([_resp(FORMS), _resp(CRITERIA)])
    doc = draft_criteria_split(client, "story", CLAIMS)
    assert [c["id"] for c in doc["criteria"]] == ["AC1", "AC2"]
    assert len(client.calls) == 2


def test_blocked_form_is_dropped_before_params():
    forms = {"forms": [
        {"claim": "quota over market", "check": "quota_vs_potential"},
        {"claim": "win rates flat", "check": "win_rate_flat"},
    ]}
    params = {"criteria": [
        {"id": "AC1", "name": "win flat", "check": "win_rate_flat",
         "params": {"band_pp": 8}, "classification": "statistical",
         "source_claim": "win rates flat"}], "ambiguities": []}
    client = FakeLLM([_resp(forms), _resp(params)])
    doc = draft_criteria_split(client, "story", {"claims": [
        {"claim": "quota over market", "classification": "COMPUTABLE"},
        {"claim": "win rates flat", "classification": "COMPUTABLE"}]})
    checks = {c["check"] for c in doc["criteria"]}
    assert "quota_vs_potential" not in checks
    assert "win_rate_flat" in checks


def test_split_returns_none_when_all_forms_blocked():
    forms = {"forms": [{"claim": "x", "check": "quota_vs_potential"}]}
    client = FakeLLM([_resp(forms)])
    out = draft_criteria_split(client, "story", {"claims": [
        {"claim": "x", "classification": "COMPUTABLE"}]})
    assert out is None


def test_draft_criteria_dispatches_to_split():
    from syngen.phases.intake import draft_criteria
    client = FakeLLM([_resp(FORMS), _resp(CRITERIA)])
    doc = draft_criteria(client, "story", claims=CLAIMS, split=True)
    assert len(doc["criteria"]) == 2
