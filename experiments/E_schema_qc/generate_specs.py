"""Experiment E: send trap stories to the LLM, collect data-spec drafts as JSON."""
import json
import time
import urllib.request
from pathlib import Path

ENDPOINT = "http://127.0.0.1:8080/v1/chat/completions"

SYSTEM_PROMPT = """You are a Business Intelligence engineer designing a synthetic dataset. Given a business story, propose the minimal set of tables needed to support analysis of that story.

Respond with ONLY a JSON object (no markdown fences, no commentary) in this exact shape:
{
  "entities": [
    {
      "name": "table_name",
      "grain": "one row per <thing>",
      "fields": [{"name": "field_name", "type": "string|decimal|date|int", "values": ["only for categorical"]}],
      "references": "name of parent table this belongs to, or null if standalone"
    }
  ]
}

Rules:
- Include only tables that store ROW-LEVEL facts or dimension attributes.
- Do NOT include pre-aggregated summary/metric tables; aggregates can be computed from fact tables.
- Use standard real-world taxonomies for business dimensions (segments, regions, industries) even if the story names only a few values."""

STORIES = {
    "T1_synonym_duplication": """Our sales team tracked opportunities through the pipeline all year. Deals that closed in Q4 carried noticeably deeper discounts than those closed earlier in the year. Deal-level analysis shows the discount creep was concentrated in EMEA accounts.

Context you may assume: fiscal year FY26 (Q1-Q4), regions AMER/EMEA/APAC.""",
    "T2_stored_aggregate": """Average win rate by quarter held at 27%, while average discount by quarter and region climbed steadily. Quarterly revenue totals by region show margins compressing every quarter.

Context you may assume: fiscal year FY26 (Q1-Q4), regions AMER/EMEA/APAC.""",
    "T3_incomplete_taxonomy": """Enterprise deals were over-allocated relative to pipeline targets, while Mid-Market was under-allocated. Discounting behavior diverged sharply between the two segments in H2.

Context you may assume: fiscal year FY26 (Q1-Q4), regions AMER/EMEA/APAC.""",
    "CONTROL_discount_erosion": """Win rates held steady this year, but average deal discounts crept up from 12% to 18%, quietly eroding margins. The bleed is worst in EMEA, where reps are discounting aggressively to close end-of-quarter deals.

Context you may assume: fiscal year FY26 (Q1-Q4), regions AMER/EMEA/APAC.""",
}


def query_llm(story):
    payload = json.dumps({
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": story},
        ],
        "temperature": 0.2,
        "max_tokens": 8192,
    }).encode("utf-8")
    req = urllib.request.Request(ENDPOINT, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    msg = body["choices"][0]["message"]
    return msg.get("content") or "", body["choices"][0].get("finish_reason")


def extract_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    return json.loads(text[start:end + 1])


def main():
    out_dir = Path("llm_specs")
    out_dir.mkdir(exist_ok=True)
    for name, story in STORIES.items():
        print(f"Querying LLM: {name} ...")
        content, finish = query_llm(story)
        try:
            spec = extract_json(content)
            path = out_dir / f"{name}.json"
            path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
            n = len(spec.get("entities", []))
            print(f"  OK -> {path} ({n} entities, finish={finish})")
        except (ValueError, json.JSONDecodeError) as e:
            path = out_dir / f"{name}.unparsed.txt"
            path.write_text(content, encoding="utf-8")
            print(f"  PARSE FAILED ({e}) -> raw saved to {path}")
        time.sleep(1)


if __name__ == "__main__":
    main()
