"""M3: story-diff classification + deterministic routing guardrails (FR8)."""
import json

import pytest

from syngen.llm.client import FakeLLM, LLMResponse
from syngen.phases.diff import (
    RoutingError,
    classify_story_change,
    validate_route,
)


def llm_json(obj):
    return LLMResponse(content=json.dumps(obj))


def test_classify_returns_parsed_route():
    client = FakeLLM([llm_json({
        "route": "parametric",
        "changed_claims": ["Q4 target moved"],
        "proposed_criteria_amendments": [{"id": "AC3", "param": "target_pct",
                                          "to": 21}],
        "proposed_config_edits": [],
    })])
    result = classify_story_change(client, "old", "new", "AC1 ...",
                                   "accounts ...", log_fn=lambda *_: None)
    assert result["route"] == "parametric"


def test_classify_rejects_unknown_route():
    client = FakeLLM([llm_json({"route": "vibes", "notes": ""})])
    with pytest.raises(RoutingError, match="unknown route"):
        classify_story_change(client, "old", "new", "", "",
                              log_fn=lambda *_: None)


CRITERIA_IDS = {"AC1", "AC2", "AC3"}


def test_guardrails_parametric_must_not_touch_config():
    proposal = {"route": "parametric",
                "proposed_criteria_amendments": [],
                "proposed_config_edits": [
                    {"path": "accounts.segments.CSB", "value": 0.2}]}
    with pytest.raises(RoutingError, match="not a categorical|config edit"):
        validate_route(proposal, CRITERIA_IDS)


def test_guardrails_taxonomy_paths_enforced():
    proposal = {"route": "taxonomy", "proposed_criteria_amendments": [],
                "proposed_config_edits": [
                    {"path": "opportunities.win_rate", "value": 0.3}]}
    with pytest.raises(RoutingError, match="not a categorical value container"):
        validate_route(proposal, CRITERIA_IDS)


def test_guardrails_taxonomy_requires_edits():
    proposal = {"route": "taxonomy", "proposed_criteria_amendments": [],
                "proposed_config_edits": []}
    with pytest.raises(RoutingError, match="without any config edit"):
        validate_route(proposal, CRITERIA_IDS)


def test_guardrails_taxonomy_must_not_amend_criteria():
    proposal = {"route": "taxonomy",
                "proposed_criteria_amendments": [
                    {"id": "AC2", "param": "target_pct", "to": 13}],
                "proposed_config_edits": [
                    {"path": "accounts.segments.CSB", "value": 0.15}]}
    with pytest.raises(RoutingError, match="must not amend"):
        validate_route(proposal, CRITERIA_IDS)


def test_guardrails_unknown_criterion_id_rejected():
    proposal = {"route": "parametric",
                "proposed_criteria_amendments": [
                    {"id": "AC99", "param": "x", "to": 1}],
                "proposed_config_edits": []}
    with pytest.raises(RoutingError, match="unknown criterion AC99"):
        validate_route(proposal, CRITERIA_IDS)


def test_guardrails_structural_always_accepted():
    proposal = {"route": "structural", "notes": "needs pipeline stages",
                "proposed_criteria_amendments": [], "proposed_config_edits": []}
    assert validate_route(proposal, CRITERIA_IDS) is proposal


VALID_PARAMETRIC = {"route": "parametric",
                    "proposed_criteria_amendments": [
                        {"id": "AC3", "param": "target_pct", "to": 21}],
                    "proposed_config_edits": []}
VALID_TAXONOMY = {"route": "taxonomy", "proposed_criteria_amendments": [],
                  "proposed_config_edits": [
                      {"path": "accounts.segments.CSB", "value": 0.1}]}
