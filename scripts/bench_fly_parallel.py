"""Parallel fleet benchmark (P10 step 3).

Fly N stories concurrently, one process per scenario, into isolated session
folders, then aggregate. Works with the local llama.cpp endpoint OR a hosted
OpenAI-compatible provider (pass --llm-config).

    python scripts/bench_fly_parallel.py --jobs 10 --limit 10 \
        --llm-config llm_configs/deepseek.example.json

Each worker writes only its own out/{scenario}_report.json and its own
session folder; the parent aggregates into benchmark_report.json, so there is
no shared-write race (the sequential runner's single shared file is why this
exists).
"""
import argparse
import io
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from syngen.fly import run_fly, summarize_reports  # noqa: E402
from syngen.llm.client import LLMClient, load_llm_config  # noqa: E402


def _fly_one(task):
    """Worker: fly one scenario in its own process. Returns the report."""
    name, story, sessions_dir, out_dir, llm_config = task
    client = LLMClient(load_llm_config(llm_config))
    t0 = time.time()
    report = run_fly(story, client, sessions_dir=sessions_dir,
                     slug=f"bench_{name}")
    report["scenario"] = name
    report["elapsed_s"] = round(time.time() - t0, 1)
    (Path(out_dir) / f"{name}_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--stories-dir", default="uat")
    ap.add_argument("--out", default="experiments/fly_benchmark")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--llm-config", default=None)
    args = ap.parse_args()

    stories = sorted(Path(args.stories_dir).glob("scenario_*"))
    stories = stories[args.offset:]
    if args.limit:
        stories = stories[:args.limit]
    if not stories:
        print(f"no scenario_* folders found in {args.stories_dir}")
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir = str(out_dir / "sessions")

    tasks = []
    for folder in stories:
        sf = folder / "story.md"
        if sf.exists():
            tasks.append((folder.name, sf.read_text(encoding="utf-8"),
                          sessions_dir, str(out_dir), args.llm_config))
    print(f"flying {len(tasks)} scenarios with {args.jobs} workers...")

    reports = []
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futures = {ex.submit(_fly_one, t): t[0] for t in tasks}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                report = fut.result()
            except Exception as e:  # noqa: BLE001 - a worker crash is a finding
                report = {"status": "error",
                          "reason": f"{type(e).__name__}: {e}",
                          "scenario": name}
            reports.append(report)
            print(f"{name}: {report['status']} "
                  f"({report.get('iterations', '-')} iters, "
                  f"{report.get('elapsed_s', '-')}s)"
                  + (f" reason={report['reason']}"
                     if report.get("reason") else ""), flush=True)

    reports.sort(key=lambda r: r.get("scenario", ""))
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
