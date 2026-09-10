"""Skills A/B (P10 step 2).

Run the criteria probe with and without the P9.1 authoring guide, K times per
story, and report Gate-1 survival, reachability survival (with --with-config),
failure classes, and token cost per arm.

    python scripts/ab_skills.py --limit 5 --runs 3 --with-config

The probe stops before the tuning loop, so a full A/B is minutes, not hours.
"""
import argparse
import io
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

from syngen.llm.client import LLMClient, load_llm_config  # noqa: E402
from syngen.probe import probe_criteria  # noqa: E402


def _classify(res):
    """Bucket deterministic failures into the classes the guide targets."""
    findings = (res.get("lint_hard") or []) + (res.get("geometry_findings") or [])
    low = " ".join(findings).lower()
    classes = []
    if "not in the pack's check registry" in low:
        classes.append("unknown_check")
    if "vacuous" in low:
        classes.append("vacuous_threshold")
    if "outside the data model" in low or "pseudo" in low:
        classes.append("pseudo_unit")
    if "unreachable" in low:
        classes.append("unreachable_target")
    if "jointly unsatisfiable" in low:
        classes.append("conflicting_bands")
    if res.get("coverage") == "uncovered":
        classes.append("coverage_uncovered")
    return classes


def _arm_summary(rows):
    n = len(rows) or 1

    def rate(key):
        return round(sum(1 for r in rows if r.get(key)) / n * 100, 1)

    usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
             "total_tokens": 0}
    classes = {}
    for r in rows:
        u = r.get("llm_usage") or {}
        for k in usage:
            usage[k] += u.get(k, 0) or 0
        for c in _classify(r):
            classes[c] = classes.get(c, 0) + 1
    reachable = [r for r in rows if "reachable_pass" in r]
    return {
        "probes": len(rows),
        "gate1_pass_rate_pct": rate("gate1_pass"),
        "reachable_pass_rate_pct": (
            round(sum(1 for r in reachable if r["reachable_pass"])
                  / len(reachable) * 100, 1) if reachable else None),
        "avg_total_tokens": round(usage["total_tokens"] / n, 1),
        "usage_totals": usage,
        "failure_classes": classes,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stories-dir", default="uat")
    ap.add_argument("--out", default="experiments/skills_ab")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--with-config", action="store_true",
                    help="also draft a config and run calibration + geometry "
                         "(catches unreachable/pseudo-unit classes)")
    ap.add_argument("--no-critic", action="store_true")
    ap.add_argument("--arms", choices=("both", "skills", "no_skills"),
                    default="both", help="run one arm or both")
    ap.add_argument("--llm-config", default=None)
    args = ap.parse_args()

    stories = sorted(Path(args.stories_dir).glob("scenario_*"))
    if args.limit:
        stories = stories[:args.limit]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl = out_dir / "ab_skills.jsonl"

    arms = [("skills", True), ("no_skills", False)]
    if args.arms != "both":
        arms = [(a, a == "skills") for a in (args.arms,)]

    rows = {"skills": [], "no_skills": []}
    for folder in stories:
        story_file = folder / "story.md"
        if not story_file.exists():
            continue
        story = story_file.read_text(encoding="utf-8")
        for run in range(args.runs):
            for arm, use_skills in arms:
                client = LLMClient(load_llm_config(args.llm_config))
                t0 = time.time()
                res = probe_criteria(client, story, use_skills=use_skills,
                                     use_critic=not args.no_critic,
                                     with_config=args.with_config)
                res.update({"scenario": folder.name, "run": run + 1, "arm": arm,
                            "elapsed_s": round(time.time() - t0, 1)})
                rows[arm].append(res)
                # incremental, so a long run is observable and a kill loses
                # at most the in-flight probe
                with open(jsonl, "a", encoding="utf-8") as f:
                    f.write(json.dumps(res) + "\n")
                extra = (" reachable="
                         + ("PASS" if res.get("reachable_pass") else "FAIL")
                         if "reachable_pass" in res else "")
                print(f"{folder.name} run{run + 1} [{arm}]: "
                      f"gate1={'PASS' if res['gate1_pass'] else 'FAIL'}{extra} "
                      f"tokens={res['llm_usage'].get('total_tokens', 0)} "
                      f"({res['elapsed_s']}s)", flush=True)

    summary = {arm: _arm_summary(rs) for arm, rs in rows.items()}
    (out_dir / "ab_skills.json").write_text(
        json.dumps({"config": vars(args), "summary": summary, "rows": rows},
                   indent=2), encoding="utf-8")
    print("\n=== SKILLS A/B SUMMARY ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
