import pytest

from syngen.llm.client import DEFAULT_CONFIG, FakeLLM, LLMClient, LLMResponse


def test_fake_returns_scripted_response():
    fake = FakeLLM([LLMResponse(content="hello")])
    r = fake.chat("sys", "user")
    assert r.content == "hello"
    assert fake.calls[0]["system"] == "sys"


def test_empty_content_retries_with_doubled_budget():
    class CountingLLM(LLMClient):
        def __init__(self):
            super().__init__(config={"max_attempts": 3})
            self.budgets = []

        def _call(self, system, user, max_tokens, temperature, attempt, effort, enable_thinking=None, reasoning_budget_tokens=None):
            self.budgets.append(max_tokens)
            if attempt < 3:
                return LLMResponse(content="", finish_reason="length", attempts=attempt)
            return LLMResponse(content="finally", attempts=attempt)

    llm = CountingLLM()
    r = llm.chat("s", "u", max_tokens=1000)
    assert r.content == "finally"
    assert r.attempts == 3
    assert llm.budgets == [1000, 2000, 4000]


def test_gives_up_after_max_attempts_returning_last():
    responses = [LLMResponse(content="")] * 5

    class Scripted(LLMClient):
        def __init__(self):
            super().__init__(config={"max_attempts": 3})
            self.queue = list(responses)

        def _call(self, system, user, max_tokens, temperature, attempt, effort, enable_thinking=None, reasoning_budget_tokens=None):
            return self.queue.pop(0)

    r = Scripted().chat("s", "u")
    assert r.content == "" and r.attempts == 3


def test_reasoning_content_captured():
    fake = FakeLLM([LLMResponse(content="ans", reasoning="thinking")])
    r = fake.chat("s", "u")
    assert r.reasoning == "thinking"


def test_retry_budget_capped_at_max_retry_tokens():
    class BudgetSpy(LLMClient):
        def __init__(self):
            super().__init__(config={"max_attempts": 3, "max_retry_tokens": 6000})
            self.budgets = []

        def _call(self, system, user, max_tokens, temperature, attempt, effort, enable_thinking=None, reasoning_budget_tokens=None):
            self.budgets.append(max_tokens)
            return LLMResponse(content="ok", attempts=attempt)

    llm = BudgetSpy()
    llm.chat("s", "u", max_tokens=5000)
    assert llm.budgets == [5000]


def test_retry_caps_at_limit_when_empty():
    spy = {}

    class EmptyLLM(LLMClient):
        def __init__(self):
            super().__init__(config={"max_attempts": 3, "max_retry_tokens": 6000})
            self.budgets = []
            spy["llm"] = self

        def _call(self, system, user, max_tokens, temperature, attempt, effort, enable_thinking=None, reasoning_budget_tokens=None):
            self.budgets.append(max_tokens)
            return LLMResponse(content="", attempts=attempt)

    r = EmptyLLM().chat("s", "u", max_tokens=4000)
    assert r.attempts == 3
    assert spy["llm"].budgets == [4000, 6000, 6000]


def test_profiles_cover_all_registered_checks_tasks():
    from syngen.llm.profiles import PROFILES, profile_for
    assert set(PROFILES) == {"decompose", "precheck", "personas",
                             "simulator_draft", "knob_proposal", "story_diff",
                             "coverage_audit", "critic"}
    for name in PROFILES:
        p = profile_for(name)
        assert p["max_tokens"] <= 16384
        assert p.get("enable_thinking") in (True, False, None)
        budget = p.get("reasoning_budget_tokens")
        assert budget is None or (isinstance(budget, int) and 0 < budget <= 8000)
        assert 1 <= p.get("max_attempts", 3) <= 3
    with pytest.raises(KeyError):
        profile_for("nonexistent")


@pytest.mark.live
def test_live_endpoint_smoke():
    """Live test against local llama.cpp. Run: pytest -m live"""
    llm = LLMClient()
    r = llm.chat(
        "Reply with exactly one word.",
        "Say: working",
        max_tokens=DEFAULT_CONFIG["max_tokens"],
    )
    assert "working" in r.content.lower()
