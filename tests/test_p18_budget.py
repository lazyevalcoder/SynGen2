"""P18: per-flight LLM budget guard (runaway protection)."""
import pytest

from syngen.llm.client import (HOSTED_BUDGET_DEFAULTS, BudgetExceeded,
                               LLMClient, LLMResponse)


def _resp():
    return LLMResponse(content="ok", usage={"total_tokens": 10})


def test_hosted_defaults_applied():
    c = LLMClient(config={"backend": "openai", "api_base": "https://x/v1"})
    assert c.config["max_calls"] == HOSTED_BUDGET_DEFAULTS["max_calls"]
    assert c.config["max_total_tokens"] == \
        HOSTED_BUDGET_DEFAULTS["max_total_tokens"]
    assert c.config["max_seconds"] == HOSTED_BUDGET_DEFAULTS["max_seconds"]


def test_local_backend_has_no_default_caps():
    c = LLMClient(config={"backend": "llamacpp"})
    assert c.config["max_calls"] is None
    assert c.config["max_total_tokens"] is None


def test_allow_unbounded_skips_defaults():
    c = LLMClient(config={"backend": "openai", "allow_unbounded": True})
    assert c.config["max_calls"] is None


def test_check_budget_raises_on_calls():
    c = LLMClient(config={"backend": "llamacpp", "max_calls": 2})
    c.usage["calls"] = 2
    with pytest.raises(BudgetExceeded, match="calls"):
        c.check_budget()


def test_check_budget_raises_on_tokens():
    c = LLMClient(config={"backend": "llamacpp", "max_total_tokens": 100})
    c.usage["total_tokens"] = 100
    with pytest.raises(BudgetExceeded, match="tokens"):
        c.check_budget()


def test_check_budget_raises_on_usd():
    c = LLMClient(config={"backend": "llamacpp", "max_usd": 0.01,
                          "price_per_mtok_in": 1.0,
                          "price_per_mtok_out": 1.0})
    c.usage["prompt_tokens"] = 20000  # ~$0.02
    with pytest.raises(BudgetExceeded, match="usd"):
        c.check_budget()


def test_chat_checks_budget_before_calling(monkeypatch):
    calls = {"n": 0}

    def fake_call(*a, **k):
        calls["n"] += 1
        return _resp()

    c = LLMClient(config={"backend": "llamacpp", "max_calls": 1})
    monkeypatch.setattr(c, "_call_resilient", fake_call)
    c.chat("s", "u")
    with pytest.raises(BudgetExceeded):
        c.chat("s", "u")
    assert calls["n"] == 1
