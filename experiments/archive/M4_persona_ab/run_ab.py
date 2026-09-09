"""M4 Phase 4: persona critique A/B (GAPS G1 verdict experiment).

For each story, run the full pipeline twice:
  arm "personas"    - as shipped (persona critique feeds spec notes)
  arm "control"     - personas skipped, simulator drafted from criteria alone

Measured per arm: convergence status, iterations, LLM proposals, elapsed
seconds, and lint findings on the final simulator draft. Verdict recorded
in README.md + GAPS log after the run.

Usage: python experiments/M4_persona_ab/run_ab.py [--stories N]
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from syngen.llm.client import LLMClient, load_llm_config  # noqa: E402
from syngen.linter import lint  # noqa: E402
from syngen.pipeline import run_new_story  # noqa: E402

STORIES = {
    "discount": ("Win rates held steady this year, but average deal discounts "
                 "crept up from 12% to 18%, quietly eroding margins. The bleed "
                 "is worst in EMEA, where reps are discounting aggressively to "
                 "close end-of-quarter deals."),
    "quota": ("Enterprise missed its quarterly revenue plan by about 5 percent "
              "in every quarter of FY26, while Mid-Market beat its plan by "
              "roughly 4 percent each quarter. The two segments offset each "
              "other, so overall revenue looked on target."),
    "slowdown": ("Our sales cycle stretched noticeably this year: deals that "
                 "closed in Q1 took about 45 days from creation to close, but "
                 "by Q4 the average cycle had grown to roughly 70 days. At the "
                 "same time pipeline creation slowed, with about 20 percent "
                 "fewer opportunities created in Q4 than in Q1. Win rates "
                 "stayed essentially flat across the year."),
}

OUT = Path(__file__).parent / "results.jsonl"
SESSIONS = Path(__file__).parent / "ab_sessions"


class MetricsIO:
    """Batch IO: accept all defaults silently."""

    def inform(self, text):
        pass

    def confirm(self, prompt, default=True):
        return default

    def ask(self, prompt, default=""):
        return default

    def free_text(self, prompt):
        return ""


def lint_counts(session_dir):
    sim = json.loads((Path(session_dir) / "simulator.json").read_text(
        encoding="utf-8"))
    findings = lint(sim)
    blocking = sum(1 for _, sev, _ in findings if sev == "FAIL")
    advise = sum(1 for _, sev, _ in findings if sev == "ADVISE")
    return blocking, advise


def run_arm(client, story, slug, use_personas):
    t0 = time.time()
    result = run_new_story(client, story, MetricsIO(),
                           sessions_dir=str(SESSIONS), slug=slug,
                           max_iterations=6, use_personas=use_personas)
    elapsed = round(time.time() - t0, 1)
    row = {"slug": slug, "arm": "personas" if use_personas else "control",
           "status": result["status"], "iterations": result.get("iterations"),
           "llm_proposals": result.get("llm_proposals"), "elapsed_s": elapsed}
    session_dir = result.get("session")
    if session_dir and (Path(session_dir) / "simulator.json").exists():
        blocking, advise = lint_counts(session_dir)
        row["lint_blocking"] = blocking
        row["lint_advise"] = advise
    return row


def main():
    limit = int(sys.argv[sys.argv.index("--stories") + 1]) if "--stories" in sys.argv else len(STORIES)
    client = LLMClient(load_llm_config())
    rows = []
    for i, (name, story) in enumerate(STORIES.items()):
        if i >= limit:
            break
        for arm, flag in (("personas", True), ("control", False)):
            print(f"=== {name} / {arm} ===", flush=True)
            try:
                row = run_arm(client, story, f"{name}_{arm}", flag)
            except Exception as e:
                row = {"slug": name, "arm": arm, "status": f"error: {e}"}
            rows.append(row)
            print(json.dumps(row), flush=True)
            with open(OUT, "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
    print("\nDone. Summary:")
    for r in rows:
        print(f"  {r['slug']:<10} {r['arm']:<9} status={r.get('status')} "
              f"iters={r.get('iterations')} proposals={r.get('llm_proposals')} "
              f"elapsed={r.get('elapsed_s')}s lint={r.get('lint_blocking')}/"
              f"{r.get('lint_advise')}")


if __name__ == "__main__":
    main()
