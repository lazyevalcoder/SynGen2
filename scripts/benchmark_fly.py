"""Fleet benchmark: fly N fresh stories unassisted, report landing rate.

Usage (requires the local LLM endpoint):
    python scripts/benchmark_fly.py --stories-dir uat \
        --out experiments/fly_benchmark

Each uat/scenario_NN/story.md is flown through `run_fly` in a fresh
session; results aggregate into benchmark_report.json with the
flight-model metrics (unassisted landing rate, escalation causes).
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

from syngen.fly import run_fly, summarize_reports  # noqa: E402
from syngen.llm.client import LLMClient, load_llm_config  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stories-dir", default="uat",
                    help="directory containing scenario_NN/story.md files")
    ap.add_argument("--out", default="experiments/fly_benchmark",
                    help="output directory for the benchmark report")
    ap.add_argument("--llm-config", default=None)
    ap.add_argument("--limit", type=int, default=0,
                    help="fly only N scenarios (0 = all)")
    ap.add_argument("--offset", type=int, default=0,
                    help="skip the first N scenarios in sorted order")
    args = ap.parse_args()

    stories = sorted(Path(args.stories_dir).glob("scenario_*"))
    stories = stories[args.offset:]
    if args.limit:
        stories = stories[:args.limit]
    if not stories:
        print(f"no scenario_* folders found in {args.stories_dir}")
        return 2

    client = LLMClient(load_llm_config(args.llm_config))
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    reports = []
    for folder in stories:
        story_file = folder / "story.md"
        if not story_file.exists():
            continue
        story = story_file.read_text(encoding="utf-8")
        t0 = time.time()
        report = run_fly(story, client, sessions_dir=str(out_dir / "sessions"),
                         slug=f"bench_{folder.name}")
        report["scenario"] = folder.name
        report["elapsed_s"] = round(time.time() - t0, 1)
        reports.append(report)
        # persist BEFORE printing: a cut/crash after the print line must
        # never lose the flight record (bench s06 lesson)
        (out_dir / f"{folder.name}_report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8")
        print(f"{folder.name}: {report['status']} "
              f"({report.get('iterations', '-')} iters, "
              f"{report['elapsed_s']}s)"
              + (f" reason={report['reason']}" if report.get("reason") else ""))

    summary = summarize_reports(reports)
    (out_dir / "benchmark_report.json").write_text(
        json.dumps({"summary": summary,
                    "reports": [{k: v for k, v in r.items()
                                 if k != "telemetry"} for r in reports]},
                   indent=2), encoding="utf-8")
    print("\n=== FLEET SUMMARY ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
