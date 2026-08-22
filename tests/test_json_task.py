"""chat_json resilience: malformed LLM output gets a corrective re-ask."""
import json

from syngen.llm.client import FakeLLM, LLMResponse
from syngen.phases.json_task import chat_json


def test_first_try_parses():
    client = FakeLLM([LLMResponse(content='{"a": 1}')])
    assert chat_json(client, "precheck", "sys", "user") == {"a": 1}


def test_malformed_then_good_retries_with_feedback():
    client = FakeLLM([
        LLMResponse(content="Sorry, I cannot comply."),
        LLMResponse(content='{"ok": true}'),
    ])
    result = chat_json(client, "precheck", "sys", "user")
    assert result == {"ok": True}
    second_call_user = client.calls[1]["user"]
    assert "not parsable" in second_call_user
    assert "Sorry, I cannot comply."[:40] in second_call_user


def test_all_attempts_fail_raises_with_context():
    client = FakeLLM([LLMResponse(content="nope")] * 3)
    try:
        chat_json(client, "personas", "sys", "user")
        raised = False
    except ValueError as e:
        raised = True
        assert "3 attempts" in str(e)
        assert len(client.calls) == 3
    assert raised


def test_fenced_output_accepted():
    fenced = "```json\n" + json.dumps({"entities": []}) + "\n```"
    client = FakeLLM([LLMResponse(content=fenced)])
    assert chat_json(client, "simulator_draft", "s", "u") == {"entities": []}
