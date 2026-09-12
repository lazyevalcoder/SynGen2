"""P11 split stage 3: block-by-block draft, deterministic assembly."""
import json

from syngen.llm.client import FakeLLM, LLMResponse
from syngen.phases.stage3 import DEFAULT_TIME_MODEL, split_simulator

from test_pipeline import BROKEN_SIM


def _resp(obj):
    return LLMResponse(content=json.dumps(obj))


CORE = {"accounts": BROKEN_SIM["accounts"],
        "opportunities": BROKEN_SIM["opportunities"]}

PRODUCTS = {
    "catalog": [{"id": "e", "tier": "entry", "share": 0.5},
                {"id": "c", "tier": "core", "share": 0.3},
                {"id": "p", "tier": "premium", "share": 0.2}],
    "margin_by_tier": {"entry": 0.45, "core": 0.6, "premium": 0.75},
    "price_multiplier_by_tier": {"entry": 0.4, "core": 1.0, "premium": 2.5},
    "discount_delta_pp_by_tier": {"entry": 0, "core": 0, "premium": 0},
    "cogs_inflation_by_quarter": [1.0, 1.0, 1.0, 1.0],
}


def test_split_core_only_when_no_optional_blocks_needed():
    client = FakeLLM([_resp(CORE)])
    cfg = split_simulator(client, "story", "criteria", ["win_rate_flat"])
    assert cfg["seed"] == 42
    assert cfg["time_model"]["quarter_labels"] == \
        DEFAULT_TIME_MODEL["quarter_labels"]
    assert "products" not in cfg
    assert len(client.calls) == 1


def test_split_drafts_required_optional_block():
    client = FakeLLM([_resp(CORE), _resp({"products": PRODUCTS})])
    cfg = split_simulator(client, "story", "criteria",
                          ["blended_margin_trend"])
    assert "products" in cfg
    assert len(client.calls) == 2


def test_split_retries_core_on_invalid_assembly():
    bad = {"accounts": {}, "opportunities": {}}
    client = FakeLLM([_resp(bad), _resp(CORE)])
    cfg = split_simulator(client, "story", "criteria", ["win_rate_flat"],
                          max_redrafts=1)
    assert cfg["accounts"]["count"] == 40
    assert len(client.calls) == 2


def test_draft_simulator_dispatches_to_split():
    from syngen.phases.spec import draft_simulator
    client = FakeLLM([_resp(CORE)])
    cfg = draft_simulator(client, "story", "criteria",
                          checks=["win_rate_flat"], split=True)
    assert cfg["accounts"]["count"] == 40
