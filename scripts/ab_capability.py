"""Capability workbench A/B (experiment): replay the recorded failures.

For each recorded failure with a criteria doc AND a drafted config, measure
how many criteria are UNBUILDABLE before vs after the stage-2/3 workbench
(numeric re-draft + deterministic snap). Also compares prompt size:
the old rulebook vs the numeric capability sheet.

    python scripts/ab_capability.py --llm-config llm_configs/local.json
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

from syngen.capability import assess_config, capability_sheet  # noqa: E402
from syngen.llm.client import LLMClient, load_llm_config  # noqa: E402
from syngen.phases.intake import authoring_guide  # noqa: E402


class _StubSession:
    def __init__(self):
        self.root = Path(".")

    def log(self, *_a, **_k):
        pass

    def write_artifact(self, *_a, **_k):
        pass


def _n_bad(cfg, doc):
    return sum(1 for f in assess_config(cfg, doc)
               if f.get("reachable") is False)


def _discover(base):
    seen = {}
    for rep in sorted(Path(base).glob("run_*/sessions/*/fly_report.json")):
        d = rep.parent
        if not (d / "criteria.json").exists() or \
                not (d / "simulator.json").exists():
            continue
        try:
            r = json.loads(rep.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        name = r.get("scenario") or d.name
        seen[name] = d
    return [seen[k] for k in sorted(seen)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="experiments/fly_benchmark")
    ap.add_argument("--out", default="experiments/capability_ab")
    ap.add_argument("--llm-config", default=None)
    ap.add_argument("--rounds", type=int, default=3)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    sessions = _discover(args.base)
    print(f"replayable sessions with criteria+config: {len(sessions)}")

    rulebook = len(authoring_guide())
    sheet = len(capability_sheet())
    print(f"prompt context: rulebook {rulebook} chars -> capability sheet "
          f"{sheet} chars ({100.0 * sheet / max(1, rulebook):.0f}%)")

    from syngen.pipeline import _capability_workbench

    rows = []
    for d in sessions:
        story = (d / "story.md").read_text(encoding="utf-8")
        doc = json.loads((d / "criteria.json").read_text(encoding="utf-8"))
        cfg = json.loads((d / "simulator.json").read_text(encoding="utf-8"))
        cp = d / "computable_claims.json"
        claims = (json.loads(cp.read_text(encoding="utf-8"))
                  if cp.exists() else {"claims": []})
        before = _n_bad(cfg, doc)
        client = LLMClient(load_llm_config(args.llm_config))
        t0 = time.time()
        try:
            nd, adj = _capability_workbench(
                _StubSession(), client, story, doc, claims, "", cfg,
                lambda *a, **k: None, max_rounds=args.rounds)
        except Exception as e:  # noqa: BLE001 - a replay crash is a finding
            nd, adj = doc, []
            print(f"{d.name}: ERROR {type(e).__name__}: {e}")
        after = _n_bad(cfg, nd)
        row = {"session": str(d), "scenario": d.name,
               "unbuildable_before": before, "unbuildable_after": after,
               "adjustments": adj, "elapsed_s": round(time.time() - t0, 1),
               "usage": client.usage_totals()}
        rows.append(row)
        u = row["usage"]
        print(f"{d.name}: unbuildable {before} -> {after} | "
              f"adjust={len(adj)} tok={u['total_tokens']} "
              f"prompt_chars={u['prompt_chars']} ({row['elapsed_s']}s)",
              flush=True)

    (out_dir / "ab_capability.json").write_text(json.dumps(rows, indent=2),
                                                encoding="utf-8")
    n = len(rows) or 1
    affected = [r for r in rows if r["unbuildable_before"] > 0]
    fixed = sum(1 for r in affected if r["unbuildable_after"] == 0)
    summary = {
        "sessions": len(rows),
        "context_chars": {"rulebook": rulebook, "capability_sheet": sheet},
        "total_unbuildable_before": sum(r["unbuildable_before"] for r in rows),
        "total_unbuildable_after": sum(r["unbuildable_after"] for r in rows),
        "affected_sessions": len(affected),
        "affected_fixed_pct": (round(100 * fixed / len(affected), 1)
                               if affected else None),
        "total_tokens": sum(r["usage"]["total_tokens"] for r in rows),
    }
    (out_dir / "ab_capability_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print("\n=== CAPABILITY A/B SUMMARY ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
