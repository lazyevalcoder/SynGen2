"""Smoke-test the local llama.cpp endpoint: story -> acceptance criteria.

Saves the LLM's independent decomposition for comparison against
acceptance_criteria.md. Part of Experiment A.
"""
import json
import urllib.request

ENDPOINT = "http://127.0.0.1:8080/v1/chat/completions"

SYSTEM_PROMPT = """You are a senior Revenue Operations analyst. You will be given a business narrative. Your job is to reverse-engineer it into measurable acceptance criteria that a generated dataset must satisfy for the story to be true.

Rules:
- Every criterion MUST be computable from tabular data (accounts and opportunities tables). No subjective criteria.
- Give each criterion a target value and a tolerance.
- State explicitly which table columns/fields would be needed to compute it.
- Flag any claim in the story that is ambiguous or under-specified, and state the assumption you chose to resolve it."""

USER_PROMPT = """Story:
"Win rates held steady this year, but average deal discounts crept up from 12% to 18%, quietly eroding margins. The bleed is worst in EMEA, where reps are discounting aggressively to close end-of-quarter deals."

Context you may assume (not stated in the story):
- Fiscal year FY26, quarters Q1-Q4
- Regions: AMER, EMEA, APAC
- Data model: accounts table + opportunities table (list price, realized price, discount %, close date, stage, region)

Produce:
1. A numbered list of acceptance criteria with target + tolerance.
2. Required fields per criterion.
3. Ambiguities found in the story and your resolution of each."""


def main():
    payload = json.dumps({
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ],
        "temperature": 0.2,
        "max_tokens": 8192,
    }).encode("utf-8")

    req = urllib.request.Request(
        ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    msg = body["choices"][0]["message"]
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""
    finish = body["choices"][0].get("finish_reason", "unknown")
    usage = body.get("usage", {})
    model = body.get("model", "unknown")

    out = f"# LLM Decomposition — Discount Erosion Story\n\n"
    out += f"- Endpoint: {ENDPOINT}\n- Model: {model}\n- Temperature: 0.2\n"
    out += f"- Finish reason: {finish}\n- Usage: {json.dumps(usage)}\n\n"
    if reasoning:
        out += "## Reasoning (model's internal)\n\n" + reasoning + "\n\n---\n\n"
    out += "## Final answer\n\n" + content + "\n"

    path = "llm_decomposition.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"Model: {model}")
    print(f"Finish reason: {finish} | completion tokens: {usage.get('completion_tokens')}")
    print(f"Saved to {path} ({len(content)} chars content, {len(reasoning)} chars reasoning)")
    print("\n--- First 1500 chars of content ---\n")
    print(content[:1500])


if __name__ == "__main__":
    main()
