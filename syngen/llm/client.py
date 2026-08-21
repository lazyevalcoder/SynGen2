"""OpenAI-compatible LLM client with reasoning-model handling (PRD NFR3).

Treats every response as untrusted input: callers must schema-validate outputs.
Per-call task budgets/efforts come from syngen.llm.profiles (evidence-based).
"""
import json
import time
import urllib.request
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    content: str
    reasoning: str = ""
    finish_reason: str = ""
    model: str = ""
    usage: dict = field(default_factory=dict)
    attempts: int = 1
    elapsed_s: float = 0.0


DEFAULT_CONFIG = {
    "endpoint": "http://127.0.0.1:8080/v1/chat/completions",
    "model": None,
    "temperature": 0.2,
    "max_tokens": 8192,
    "timeout_s": 1200,
    "max_attempts": 3,
    "max_retry_tokens": 16384,
    "reasoning_effort": "medium",
}


def load_llm_config(path=None):
    if path is None:
        return dict(DEFAULT_CONFIG)
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    return merged


class LLMClient:
    def __init__(self, config=None, log_fn=None):
        self.config = dict(DEFAULT_CONFIG)
        if config:
            self.config.update(config)
        self.log_fn = log_fn

    def chat(self, system, user, max_tokens=None, temperature=None,
             reasoning_effort=None):
        """Send a chat completion.

        Empty content triggers retry with doubled budget, capped at
        config['max_retry_tokens'] - runaway retries were measured burning
        ~10 min per attempt on a 35B model (see PERFORMANCE_EXPECTATIONS.md).
        """
        tokens = max_tokens or self.config["max_tokens"]
        temp = self.config["temperature"] if temperature is None else temperature
        effort = reasoning_effort or self.config["reasoning_effort"]
        last = None
        for attempt in range(1, self.config["max_attempts"] + 1):
            if self.log_fn:
                self.log_fn(f"[llm] attempt {attempt} starting "
                            f"(budget={tokens}, effort={effort})")
            started = time.time()
            last = self._call(system, user, tokens, temp, attempt, effort)
            last.attempts = attempt
            last.elapsed_s = time.time() - started
            if self.log_fn:
                self.log_fn(
                    f"[llm] attempt {attempt} done in {last.elapsed_s:.1f}s - "
                    f"finish={last.finish_reason} "
                    f"tokens={last.usage.get('completion_tokens')}"
                )
            if last.content.strip():
                return last
            tokens = min(tokens * 2, self.config["max_retry_tokens"])
            if self.log_fn:
                self.log_fn(f"[llm] empty content (attempt {attempt}), "
                            f"retrying with max_tokens={tokens}")
        return last

    def _call(self, system, user, max_tokens, temperature, attempt, effort):
        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "reasoning_effort": effort,
        }
        req = urllib.request.Request(
            self.config["endpoint"], data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.config["timeout_s"]) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        msg = body["choices"][0]["message"]
        return LLMResponse(
            content=msg.get("content") or "",
            reasoning=msg.get("reasoning_content") or "",
            finish_reason=body["choices"][0].get("finish_reason", ""),
            model=str(body.get("model", "")),
            usage=dict(body.get("usage", {})),
            attempts=attempt,
        )


class FakeLLM(LLMClient):
    """Scripted offline client for unit tests. Queue of LLMResponses or callables."""

    def __init__(self, script=None):
        super().__init__(config={"max_attempts": 1})
        self.script = list(script or [])
        self.calls = []

    def _call(self, system, user, max_tokens, temperature, attempt, effort):
        self.calls.append({"system": system, "user": user,
                           "max_tokens": max_tokens, "effort": effort})
        item = self.script.pop(0) if self.script else LLMResponse(content="")
        if callable(item):
            item = item(self.calls[-1])
        return item
