import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from syngen.llm.client import LLMClient
from syngen.llm.profiles import profile_for
from syngen.prompts import load_prompt

story = Path("smoke_story.md").read_text(encoding="utf-8")
criteria = json.loads(Path("sessions/2026-08-22_smokeR1/criteria.json").read_text(encoding="utf-8"))
crit_summary = "\n".join(
    f"{c['id']} {c['name']} params={json.dumps(c['params'])}" for c in criteria["criteria"]
)
system = load_prompt("persona_critique")
user = f"Story:\n{story}\n\nAcceptance criteria:\n{crit_summary}"
p = profile_for("personas")
client = LLMClient()
r = client.chat(system, user, max_tokens=p["max_tokens"],
                reasoning_effort=p.get("reasoning_effort"),
                enable_thinking=p.get("enable_thinking"))
print("finish:", r.finish_reason, "| tokens:", r.usage.get("completion_tokens"), "| chars:", len(r.content))
Path("output_persona_debug.txt").write_text(r.content, encoding="utf-8")
print("--- first 600 ---")
print(r.content[:600])
