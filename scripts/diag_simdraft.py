"""Diagnose the simulator_draft empty-content failure using real session artifacts."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from syngen.llm.client import LLMClient
from syngen.llm.profiles import chat_task, profile_for
from syngen.prompts import load_prompt

SESSION = Path(sys.argv[1] if len(sys.argv) > 1 else "sessions/2026-08-21_smoke")

story = Path("smoke_story.md").read_text(encoding="utf-8")
criteria = json.loads((SESSION / "criteria.json").read_text(encoding="utf-8"))
crit_summary = "\n".join(
    f"{c['id']} {c['name']} params={json.dumps(c['params'])}"
    for c in criteria["criteria"]
)
spec_notes = ""
if (SESSION / "spec.md").exists():
    spec_notes = (SESSION / "spec.md").read_text(encoding="utf-8")

spec_brief = (spec_notes or "none")[-1500:]
system = load_prompt("simulator_draft", story=story[:2000],
                     criteria=crit_summary, spec=spec_brief)

p = profile_for("simulator_draft")
print(f"profile: {p}")
client = LLMClient()
r = chat_task(client, "simulator_draft", system, "Produce the simulator.json now.")

print(f"finish_reason : {r.finish_reason}")
print(f"attempts      : {r.attempts}")
print(f"elapsed_s     : {r.elapsed_s:.1f}")
print(f"completion_tok: {r.usage.get('completion_tokens')}")
print(f"content_chars : {len(r.content)}")
print(f"reasoning_len : {len(r.reasoning)}")
print("--- reasoning tail (last 400) ---")
print(r.reasoning[-400:] if r.reasoning else "(none)")
print("--- content head (first 500) ---")
print(r.content[:500] if r.content else "(empty)")

out = {
    "finish_reason": r.finish_reason,
    "completion_tokens": r.usage.get("completion_tokens"),
    "content": r.content,
    "reasoning": r.reasoning,
}
Path("output_simdraft_diag.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print("\nsaved: output_simdraft_diag.json")
