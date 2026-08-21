"""Live benchmark: measures per-task latency/tokens on the configured endpoint.
Run manually: python scripts/benchmark_llm.py [--json out.json]
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from syngen.llm.client import LLMClient
from syngen.llm.profiles import PROFILES, chat_task
from syngen.prompts import load_prompt

STORY = (
    "Discounting discipline slipped this year. Average discounts on closed deals "
    "climbed from about 10 percent in Q1 to roughly 16 percent by Q4. Win rates "
    "held near one in four opportunities all year. The deepest discounting showed "
    "up in APAC, where reps leaned on price cuts to rescue late-quarter deals."
)

CRITERIA = {
    "definitions": {},
    "criteria": [
        {"id": "AC1", "name": "q1 discount", "check": "avg_discount_quarter",
         "params": {"quarter": "FY26-Q1", "target_pct": 10.0, "tolerance_pp": 2}},
        {"id": "AC2", "name": "q4 discount", "check": "avg_discount_quarter",
         "params": {"quarter": "FY26-Q4", "target_pct": 16.0, "tolerance_pp": 2}},
    ],
}

SIM = {
    "seed": 42,
    "opportunities": {"discount": {"base_by_quarter": {
        "AMER": [10, 11, 12, 13], "APAC": [10, 11, 12, 13], "EMEA": [10, 11, 12, 13]}}},
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default=None)
    args = parser.parse_args()

    client = LLMClient()
    results = []

    def run(task, system, user):
        r = chat_task(client, task, system, user)
        row = {
            "task": task,
            "elapsed_s": round(r.elapsed_s, 1),
            "completion_tokens": r.usage.get("completion_tokens"),
            "finish_reason": r.finish_reason,
            "attempts": r.attempts,
            "content_chars": len(r.content),
            "parsed": False,
        }
        try:
            from syngen.utils import extract_json
            extract_json(r.content)
            row["parsed"] = True
        except ValueError:
            pass
        results.append(row)
        print(f"{task:<16} {row['elapsed_s']:>7}s  tokens={row['completion_tokens']}  "
              f"finish={row['finish_reason']}  parsed={row['parsed']}")
        return r

    crit_summary = "\n".join(
        f"{c['id']} {c['name']} params={json.dumps(c['params'])}"
        for c in CRITERIA["criteria"]
    )

    print(f"Benchmarking {len(PROFILES)} tasks...\n")
    run("precheck", load_prompt("precheck"), STORY)
    decompose_r = run("decompose", load_prompt("decompose", user_decisions="none", story=STORY),
                      "Produce the criteria JSON now.")
    run("personas", load_prompt("persona_critique"),
        f"Story:\n{STORY}\n\nAcceptance criteria:\n{crit_summary}")
    try:
        sim_doc = json.loads(Path("sessions").glob("*_smoke/simulator.json").__next__().read_text()) if False else None
    except Exception:
        sim_doc = None
    run("simulator_draft",
        load_prompt("simulator_draft", story=STORY, criteria=crit_summary, spec="none"),
        "Produce the simulator.json now.")
    run("knob_proposal",
        load_prompt("knob_proposal",
                    validation_results="AC5 FAIL +0.5pp vs AMER (need >= +3pp) margin -2.50",
                    iteration_history="iter 1: failed=['AC5'], changed=[]",
                    simulator_json=json.dumps(SIM, indent=2)),
        "Propose the next knob changes as JSON.")

    total = sum(r["elapsed_s"] for r in results)
    all_parsed = all(r["parsed"] for r in results)
    print(f"\nTotal measured latency: {total:.0f}s across {len(results)} calls "
          f"(one iteration of each task)")
    print(f"All outputs JSON-parseable: {all_parsed}")

    if args.json:
        payload = {
            "benchmarked_at": datetime.now().isoformat(timespec="seconds"),
            "results": results,
            "total_s": round(total, 1),
            "all_parsed": all_parsed,
        }
        Path(args.json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Saved: {args.json}")


if __name__ == "__main__":
    main()
