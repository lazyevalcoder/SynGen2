"""Probe which reasoning-control parameters this llama.cpp build honors."""
import json
import time
import urllib.request

ENDPOINT = "http://127.0.0.1:8080/v1/chat/completions"
PROMPT = ("Think step by step about how to organize a sales conference, "
          "then give one final recommendation.")


def probe(desc, extra):
    payload = {
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 8000,
    }
    payload.update(extra)
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    body = json.loads(urllib.request.urlopen(req, timeout=900).read().decode("utf-8"))
    m = body["choices"][0]["message"]
    u = body["usage"]
    print(f"{desc}: elapsed={time.time() - t0:.1f}s "
          f"finish={body['choices'][0]['finish_reason']} "
          f"tokens={u['completion_tokens']} "
          f"reasoning_chars={len(m.get('reasoning_content') or '')} "
          f"content_chars={len(m.get('content') or '')}")


probe("baseline (no controls)", {})
probe("reasoning_effort=low", {"reasoning_effort": "low"})
probe("reasoning_budget_tokens=50", {"reasoning_budget_tokens": 50})
