"""P10 step 3: hosted-provider client support.

Offline tests (urlopen monkeypatched): the openai backend must send the
Authorization header + model and must NOT send llama.cpp-only params; the
llamacpp backend keeps its exact behavior; api_key_env resolves from env.
"""
import json
import urllib.error

import pytest

from syngen.llm.client import LLMClient, load_llm_config


class _FakeResp:
    def __init__(self, body):
        self._b = json.dumps(body).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _capture(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.headers)
        seen["payload"] = json.loads(req.data.decode("utf-8"))
        seen["timeout"] = timeout
        return _FakeResp({"choices": [{"message": {"content": "{}"},
                                       "finish_reason": "stop"}],
                          "model": "m", "usage": {"total_tokens": 1}})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return seen


def test_openai_backend_headers_model_and_no_llamacpp_params(monkeypatch):
    seen = _capture(monkeypatch)
    client = LLMClient(config={
        "backend": "openai", "api_base": "https://api.deepseek.com/v1",
        "api_key": "sk-test", "model": "deepseek-chat", "timeout_s": 300,
        "headers": {"X-Title": "SynGen"},
    })
    client._call("sys", "usr", 100, 0.2, 1, "medium",
                 enable_thinking=True, reasoning_budget_tokens=400)
    assert seen["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer sk-test"
    assert seen["headers"]["X-title"] == "SynGen"
    assert seen["payload"]["model"] == "deepseek-chat"
    assert "chat_template_kwargs" not in seen["payload"]
    assert "reasoning_budget_tokens" not in seen["payload"]
    assert "reasoning_effort" not in seen["payload"]


def test_llamacpp_backend_keeps_extensions(monkeypatch):
    seen = _capture(monkeypatch)
    client = LLMClient(config={"backend": "llamacpp"})
    client._call("sys", "usr", 100, 0.2, 1, "medium",
                 enable_thinking=False, reasoning_budget_tokens=400)
    assert seen["payload"]["reasoning_effort"] == "medium"
    assert seen["payload"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert seen["payload"]["reasoning_budget_tokens"] == 400
    assert "model" not in seen["payload"]


def test_api_key_env_resolves(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_PROVIDER_KEY", "sk-from-env")
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps({
        "backend": "openai", "api_base": "https://x/v1",
        "api_key_env": "MY_PROVIDER_KEY", "model": "m"}), encoding="utf-8")
    cfg = load_llm_config(str(cfg_path))
    assert cfg["api_key"] == "sk-from-env"
    assert cfg["backend"] == "openai"


def test_api_base_overrides_endpoint(monkeypatch):
    seen = _capture(monkeypatch)
    client = LLMClient(config={"backend": "openai",
                               "api_base": "https://x/v1/",
                               "endpoint": "http://should-not-be-used"})
    client._call("s", "u", 10, 0.2, 1, "medium")
    assert seen["url"] == "https://x/v1/chat/completions"


def test_transient_http_error_is_retried(monkeypatch):
    calls = {"n": 0}

    def flaky(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {},
                                         None)
        return _FakeResp({"choices": [{"message": {"content": "ok"},
                                       "finish_reason": "stop"}],
                          "model": "m", "usage": {}})

    monkeypatch.setattr("urllib.request.urlopen", flaky)
    client = LLMClient(config={"backend": "openai",
                               "api_base": "https://x/v1",
                               "http_backoff_s": 0, "max_http_retries": 2})
    resp = client.chat("s", "u", max_attempts=1)
    assert resp.content == "ok"
    assert calls["n"] == 2


def test_nontransient_http_error_propagates(monkeypatch):
    def bad(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {},
                                     None)

    monkeypatch.setattr("urllib.request.urlopen", bad)
    client = LLMClient(config={"backend": "openai",
                               "api_base": "https://x/v1",
                               "http_backoff_s": 0, "max_http_retries": 3})
    with pytest.raises(urllib.error.HTTPError):
        client.chat("s", "u", max_attempts=1)
