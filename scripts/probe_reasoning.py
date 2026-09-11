"""Probe which reasoning-control parameters this llama.cpp build honors.

Empirically answers, repeatably (run each condition N times to separate signal
from stochastic reasoning-length variance):
  - does `reasoning_effort` change thinking volume? (documented per-request)
  - is `reasoning_budget_tokens` honored, or ignored? (undocumented field)
  - does `chat_template_kwargs.enable_thinking` disable thinking?
  - does `response_format: {"type": "json_object"}` yield parseable JSON?
  - does a server-side `--reasoning-budget N` cap bound thinking? (start the
    server with the flag; watch no run's reasoning exceed ~N tokens)

Usage:
    python scripts/probe_reasoning.py --runs 2
    python scripts/probe_reasoning.py --endpoint http://127.0.0.1:8080/v1/chat/completions
"""
import argparse
import json
import statistics
import time
import urllib.error
import urllib.request

DEFAULT_ENDPOINT = "http://127.0.0.1:8080/v1/chat/completions"

THINK_PROMPT = (
    "Think step by step about how to organize a sales conference, "
    "then give one final recommendation.")

JSON_PROMPT = ('Return a JSON object with keys "a" (integer) and "b" '
               '(string). Output only JSON.')

# (label, prompt, extra body fields)
CONDITIONS = [
    ("baseline", THINK_PROMPT, {}),
    ("effort=none", THINK_PROMPT, {"reasoning_effort": "none"}),
    ("effort=low", THINK_PROMPT, {"reasoning_effort": "low"}),
    ("effort=high", THINK_PROMPT, {"reasoning_effort": "high"}),
    ("budget=50", THINK_PROMPT, {"reasoning_budget_tokens": 50}),
    ("budget=4000", THINK_PROMPT, {"reasoning_budget_tokens": 4000}),
    ("think=off", THINK_PROMPT,
     {"chat_template_kwargs": {"enable_thinking": False}}),
    ("json_object", JSON_PROMPT,
     {"response_format": {"type": "json_object"}}),
]


def one_call(endpoint, prompt, extra, max_tokens, timeout_s):
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    payload.update(extra)
    req = urllib.request.Request(
        endpoint, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        return {"error": f"HTTP {e.code}: {detail}", "elapsed": time.time() - t0}
    except Exception as e:  # noqa: BLE001 - probe reports, never crashes
        return {"error": f"{type(e).__name__}: {e}",
                "elapsed": time.time() - t0}
    msg = body["choices"][0]["message"]
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""
    usage = body.get("usage") or {}
    try:
        json.loads(content.strip())
        valid_json = True
    except ValueError:
        valid_json = False
    return {
        "elapsed": time.time() - t0,
        "finish": body["choices"][0].get("finish_reason", ""),
        "completion_tokens": usage.get("completion_tokens"),
        "reasoning_chars": len(reasoning),
        "content_chars": len(content),
        "valid_json": valid_json,
        "content": content,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--prompt", default=THINK_PROMPT,
                    help="prompt for the thinking conditions (use a "
                         "reasoning-heavy prompt to test a server "
                         "--reasoning-budget cap)")
    ap.add_argument("--budgets", default="",
                    help="comma list of reasoning_budget_tokens to sweep "
                         "(replaces the default conditions)")
    ap.add_argument("--only", default="",
                    help="comma list of condition labels to run")
    args = ap.parse_args()

    conditions = []
    for label, prompt, extra in CONDITIONS:
        if prompt is THINK_PROMPT:
            prompt = args.prompt
        conditions.append((label, prompt, extra))
    if args.budgets.strip():
        conditions = []
        for part in args.budgets.split(","):
            part = part.strip()
            if not part:
                continue
            conditions.append((f"budget={part}", args.prompt,
                               {"reasoning_budget_tokens": int(part)}))
    if args.only.strip():
        wanted = {p.strip() for p in args.only.split(",") if p.strip()}
        conditions = [c for c in conditions if c[0] in wanted]

    print(f"endpoint: {args.endpoint}  runs/cond: {args.runs}  "
          f"max_tokens: {args.max_tokens}\n")
    header = (f"{'condition':<13} {'run':>3} {'elapsed':>8} {'finish':>8} "
              f"{'tok':>6} {'reason_ch':>9} {'content_ch':>10} {'json':>5}")
    print(header)
    print("-" * len(header))

    summary = []
    for label, prompt, extra in conditions:
        rows = []
        for r in range(1, args.runs + 1):
            res = one_call(args.endpoint, prompt, extra, args.max_tokens,
                           args.timeout)
            if "error" in res:
                print(f"{label:<13} {r:>3}  ERROR: {res['error'][:90]}")
                continue
            rows.append(res)
            print(f"{label:<13} {r:>3} {res['elapsed']:>7.1f}s "
                  f"{res['finish']:>8} {str(res['completion_tokens']):>6} "
                  f"{res['reasoning_chars']:>9} {res['content_chars']:>10} "
                  f"{str(res['valid_json']):>5}")
            if not res["valid_json"] and res["content"].strip():
                print(f"{'':<13}      content: {res['content'][:100]!r}")
        if rows:
            summary.append({
                "condition": label,
                "elapsed": round(statistics.mean(r["elapsed"] for r in rows), 1),
                "tok": int(statistics.mean(r["completion_tokens"] or 0
                                           for r in rows)),
                "rch_mean": int(statistics.mean(r["reasoning_chars"]
                                                for r in rows)),
                "rch_min": min(r["reasoning_chars"] for r in rows),
                "rch_max": max(r["reasoning_chars"] for r in rows),
                "json_ok": sum(1 for r in rows if r["valid_json"]),
                "n": len(rows),
            })

    print("\n== summary ==")
    print(f"{'condition':<13} {'elapsed':>8} {'tok':>6} {'reason_ch':>10} "
          f"{'range':>14} {'json_ok':>8}")
    for s in summary:
        print(f"{s['condition']:<13} {s['elapsed']:>7.1f}s {s['tok']:>6} "
              f"{s['rch_mean']:>10} {s['rch_min']:>6}-{s['rch_max']:<7} "
              f"{s['json_ok']}/{s['n']:<6}")

    print("\nInterpretation (verified 2026-09-11, llama.cpp + Ornith-35B):")
    print(" - baseline spread is the stochastic floor; ignore differences "
          "inside it.")
    print(" - effort=* inside baseline spread => reasoning_effort is IGNORED "
          "(even 'none' keeps thinking).")
    print(" - budget=N caps thinking ~linearly (~4-5 chars/token); budget=0 "
          "= UNLIMITED (not off).")
    print(" - think=off reason_ch ~0 => enable_thinking works (use it to "
          "disable, not budget=0).")
    print(" - json_object was NOT enforced (model still emitted fenced "
          "```json; extract_json strips fences anyway).")
    print(" - with a server --reasoning-budget N, thinking is bounded only if "
          "N is BELOW the model's natural thinking (~3k tokens here).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
