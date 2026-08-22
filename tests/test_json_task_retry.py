"""Truncation-aware retries: length-cutoff and bad-format get different fixes."""
import json

import pytest

from syngen.llm.client import FakeLLM, LLMResponse
from syngen.phases import json_task
from syngen.phases.json_task import chat_json


def make_client(script):
    return FakeLLM([LLMResponse(content=c, finish_reason=f) for c, f in script])


def test_truncated_output_escalates_budget(monkeypatch):
    monkeypatch.setattr(json_task, "profile_for",
                        lambda task: {"max_tokens": 100})
    client = make_client([
        ('{"a": [1,2', "length"),
        ('{"a": [1,2,3]}', "stop"),
    ])
    result = chat_json(client, "personas", "sys", "user")
    assert result == {"a": [1, 2, 3]}
    assert client.calls[0]["max_tokens"] == 100
    assert client.calls[1]["max_tokens"] == 200
    assert "concise" in client.calls[1]["user"]


def test_bad_format_reasks_same_budget_with_quoted_output(monkeypatch):
    monkeypatch.setattr(json_task, "profile_for",
                        lambda task: {"max_tokens": 100})
    client = make_client([
        ("Sorry, no JSON here.", "stop"),
        ('{"ok": true}', "stop"),
    ])
    result = chat_json(client, "personas", "sys", "user")
    assert result == {"ok": True}
    assert client.calls[1]["max_tokens"] == 100
    assert "not parsable" in client.calls[1]["user"]
    assert "Sorry" in client.calls[1]["user"]


def test_escalation_respects_ceiling(monkeypatch):
    monkeypatch.setattr(json_task, "profile_for",
                        lambda task: {"max_tokens": 9000})
    script = [('{"x": ', "length")] * 3
    client = make_client(script)
    with pytest.raises(ValueError, match="length"):
        chat_json(client, "personas", "sys", "user", max_parse_attempts=3)
    budgets = [c["max_tokens"] for c in client.calls]
    assert budgets == [9000, 16384, 16384]


def test_good_first_try_never_retries():
    client = make_client([('{"done": true}', "stop")])
    result = chat_json(client, "precheck", "s", "u")
    assert result == {"done": True}
    assert len(client.calls) == 1
