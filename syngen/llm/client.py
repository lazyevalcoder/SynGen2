"""OpenAI-compatible LLM client with reasoning-model handling (PRD NFR3).

Treats every response as untrusted input: callers must schema-validate outputs.
Per-call task budgets/efforts come from syngen.llm.profiles (evidence-based).
"""
import json
import time
import urllib.error
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
    # Local llama.cpp by default (unchanged behavior).
    "endpoint": "http://127.0.0.1:8080/v1/chat/completions",
    # Hosted providers (P10 step 3): set api_base (e.g.
    # "https://api.deepseek.com/v1") and it overrides endpoint; set
    # api_key or api_key_env for Authorization; set model. backend
    # "openai" omits llama.cpp-only params.
    "api_base": None,
    "api_key": None,
    "api_key_env": None,
    "model": None,
    "headers": {},
    "backend": "llamacpp",   # "llamacpp" | "openai"
    "temperature": 0.2,
    "max_tokens": 8192,
    "timeout_s": 1200,
    "max_attempts": 3,
    "max_retry_tokens": 16384,
    "reasoning_effort": "medium",
    # Hosted providers rate-limit (429) and have transient 5xx; retry with
    # exponential backoff, honouring Retry-After. Applies to every call.
    "max_http_retries": 3,
    "http_backoff_s": 2.0,
    # Extra body fields passed through verbatim (e.g. OpenRouter's
    # {"provider": {"sort": "throughput"}} or {"response_format": ...}).
    "body_extras": {},
    # Scale the per-task reasoning_budget_tokens (llama.cpp only), e.g. 0.25
    # for a faster local run. Verified honored (probe 2026-09-11): budget N
    # caps thinking at ~N tokens; budget=0 means UNLIMITED (use
    # enable_thinking=False to disable thinking). None = untouched.
    "reasoning_budget_scale": None,
}


def load_llm_config(path=None):
    if path is None:
        return dict(DEFAULT_CONFIG)
    with open(path, encoding="utf-8-sig") as f:
        cfg = json.load(f)
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    # Resolve the API key from the environment so secrets never live in a
    # file. An explicit api_key in the config still wins.
    if not merged.get("api_key") and merged.get("api_key_env"):
        import os
        merged["api_key"] = os.environ.get(merged["api_key_env"]) or None
    return merged


class LLMClient:
    def __init__(self, config=None, log_fn=None):
        self.config = dict(DEFAULT_CONFIG)
        if config:
            self.config.update(config)
        self.log_fn = log_fn
        # Per-client usage accumulator (P10 step 1): one client drives one
        # flight, so these totals are the flight's LLM cost. Reasoning
        # models may bill hidden thinking tokens the endpoint reports in
        # completion_tokens; we take whatever the endpoint returns.
        self.usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                      "total_tokens": 0, "elapsed_s": 0.0}

    def usage_totals(self):
        """Copy of the accumulated usage for this client (per-flight)."""
        return dict(self.usage)

    def _accumulate_usage(self, resp):
        u = resp.usage or {}
        self.usage["calls"] += 1
        self.usage["prompt_tokens"] += int(u.get("prompt_tokens") or 0)
        self.usage["completion_tokens"] += int(u.get("completion_tokens") or 0)
        total = u.get("total_tokens")
        if total is None:
            total = (int(u.get("prompt_tokens") or 0)
                     + int(u.get("completion_tokens") or 0))
        self.usage["total_tokens"] += int(total or 0)
        self.usage["elapsed_s"] = round(
            self.usage["elapsed_s"] + float(resp.elapsed_s or 0.0), 2)

    def chat(self, system, user, max_tokens=None, temperature=None,
             reasoning_effort=None, max_attempts=None, enable_thinking=None,
             reasoning_budget_tokens=None):
        """Send a chat completion.

        Reasoning controls on llama.cpp (probe 2026-09-11, Ornith-35B):
        - reasoning_effort: IGNORED by llama.cpp (even "none" keeps thinking);
          kept only for OpenAI-compatible endpoints.
        - enable_thinking=False via chat_template_kwargs: verified working
          (the way to turn thinking OFF).
        - reasoning_budget_tokens=N: verified working - caps thinking at ~N
          tokens (~4-5 chars/token). N=0 means UNLIMITED, not off.
        Empty content triggers retry with doubled budget, capped at
        config['max_retry_tokens'].
        """
        tokens = max_tokens or self.config["max_tokens"]
        temp = self.config["temperature"] if temperature is None else temperature
        effort = reasoning_effort or self.config["reasoning_effort"]
        think = self.config.get("enable_thinking") if enable_thinking is None else enable_thinking
        budget = self.config.get("reasoning_budget_tokens") if reasoning_budget_tokens is None else reasoning_budget_tokens
        scale = self.config.get("reasoning_budget_scale")
        if budget is not None and scale is not None:
            budget = max(0, int(float(budget) * float(scale)))
        attempts_allowed = max_attempts if max_attempts else self.config["max_attempts"]
        last = None
        for attempt in range(1, attempts_allowed + 1):
            if self.log_fn:
                self.log_fn(f"[llm] attempt {attempt} starting "
                            f"(budget={tokens}, effort={effort}, think={think}, "
                            f"think_budget={budget})")
            started = time.time()
            last = self._call_resilient(system, user, tokens, temp, attempt,
                                        effort, think, budget)
            last.attempts = attempt
            last.elapsed_s = time.time() - started
            self._accumulate_usage(last)
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

    _TRANSIENT_HTTP = (408, 409, 429, 500, 502, 503, 504)

    def _retry_after(self, err, default):
        headers = getattr(err, "headers", None)
        raw = headers.get("Retry-After") if headers else None
        try:
            return max(default, float(raw))
        except (TypeError, ValueError):
            return default

    def _call_resilient(self, *args):
        """Call with retry/backoff on transient HTTP errors (P10 step 3).

        Hosted providers rate-limit (429) and hiccup (5xx); a single such
        response must not kill a flight. Honours Retry-After. Non-transient
        errors (401/400/...) propagate immediately - they are config bugs,
        not noise.
        """
        retries = int(self.config.get("max_http_retries", 3) or 0)
        backoff = float(self.config.get("http_backoff_s", 2.0) or 2.0)
        for i in range(retries + 1):
            try:
                return self._call(*args)
            except urllib.error.HTTPError as e:
                if e.code not in self._TRANSIENT_HTTP or i >= retries:
                    raise
                wait = self._retry_after(e, backoff * (2 ** i))
                if self.log_fn:
                    self.log_fn(f"[llm] HTTP {e.code} - retry {i + 1}/"
                                f"{retries} in {wait:.1f}s")
                time.sleep(wait)
            except urllib.error.URLError as e:
                if i >= retries:
                    raise
                wait = backoff * (2 ** i)
                if self.log_fn:
                    self.log_fn(f"[llm] network error ({e}) - retry {i + 1}/"
                                f"{retries} in {wait:.1f}s")
                time.sleep(wait)

    def _endpoint(self):
        base = self.config.get("api_base")
        if base:
            return base.rstrip("/") + "/chat/completions"
        return self.config["endpoint"]

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.config.get("api_key"):
            headers["Authorization"] = f"Bearer {self.config['api_key']}"
        extra = self.config.get("headers") or {}
        if isinstance(extra, dict):
            headers.update({str(k): str(v) for k, v in extra.items()})
        return headers

    def _call(self, system, user, max_tokens, temperature, attempt, effort,
              enable_thinking=None, reasoning_budget_tokens=None):
        backend = self.config.get("backend", "llamacpp")
        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self.config.get("model"):
            payload["model"] = self.config["model"]
        if backend == "llamacpp":
            # llama.cpp extensions (hosted OpenAI-compatible APIs ignore or
            # reject unknown fields, so only send them locally).
            # Probe 2026-09-11: reasoning_effort is IGNORED by this build
            # (even "none" does not disable thinking); chat_template_kwargs
            # enable_thinking and reasoning_budget_tokens are HONORED.
            payload["reasoning_effort"] = effort
            if enable_thinking is not None:
                payload["chat_template_kwargs"] = {
                    "enable_thinking": enable_thinking}
            if reasoning_budget_tokens is not None:
                payload["reasoning_budget_tokens"] = reasoning_budget_tokens
        else:
            # Hosted OpenAI-compatible providers (OpenRouter et al): control
            # reasoning via the `reasoning` object. Mechanical JSON tasks
            # (enable_thinking=False) run with effort "none"; thinking tasks
            # use the configured effort (default "low"). Note: OpenRouter's
            # schema has no reasoning.max_tokens - `effort` is the lever.
            reff = "none" if enable_thinking is False else (effort or "low")
            payload["reasoning"] = {"effort": reff}
        # Extra body fields passed through verbatim for BOTH backends, applied
        # last so they can override defaults (e.g. {"response_format": ...}).
        extras = self.config.get("body_extras") or {}
        if isinstance(extras, dict):
            payload.update(extras)
        req = urllib.request.Request(
            self._endpoint(), data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(), method="POST",
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

    def _call(self, system, user, max_tokens, temperature, attempt, effort,
              enable_thinking=None, reasoning_budget_tokens=None):
        self.calls.append({"system": system, "user": user,
                           "max_tokens": max_tokens, "effort": effort,
                           "enable_thinking": enable_thinking})
        item = self.script.pop(0) if self.script else LLMResponse(content="")
        if callable(item):
            item = item(self.calls[-1])
        return item
