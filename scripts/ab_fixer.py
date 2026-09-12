"""Defect-Response A/B (experiment): replay the recorded rework step.

We already paid for the failing flights. This harness reconstructs each
failure's final escalation (judge verdict + evidence) from its session and
runs the rework step under two arms:

  A classic - redraft_criteria (full context: story + ~7.5k catalog + ~5.5k guide)
  B defect  - work order -> runbook/fixer -> verify (minimal context)

Metrics per arm: tokens, prompt chars (signal size), lint pass, source-claim
preservation, resolver used, and whether the defect class was addressed.

    python scripts/ab_fixer.py --llm-config llm_configs/local.json
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
from syngen.phases import defect_response as dr  # noqa: E402
from syngen.phases.criteria_lint import lint_criteria_internal  # noqa: E402
from syngen.phases.rework import redraft_criteria  # noqa: E402


def _load_session(d):
    d = Path(d)
    story = (d / "story.md").read_text(encoding="utf-8")
    doc = json.loads((d / "criteria.json").read_text(encoding="utf-8"))
    rep = json.loads((d / "fly_report.json").read_text(encoding="utf-8"))
    cp = d / "computable_claims.json"
    claims = (json.loads(cp.read_text(encoding="utf-8"))
              if cp.exists() else {"claims": []})
    return story, doc, rep, claims


def _last_verdict(rep):
    dirs = (rep.get("rework") or {}).get("directives") or []
    if not dirs:
        return None, None
    d = dirs[-1]
    verdict = {"action": d.get("action") or "rework_criteria",
               "scope": d.get("scope") or [],
               "reason": d.get("reason") or "",
               "guidance": d.get("guidance") or ""}
    evidence = {"kind": d.get("kind") or "unknown",
                "reason": rep.get("reason") or "",
                "detail": d.get("reason") or ""}
    return verdict, evidence


def _has_ceiling(c):
    return any(str(k).startswith("max_") for k in (c.get("params") or {}))


def _measure(orig, new, targets, defect):
    hard, _ = lint_criteria_internal(new)
    ob = {c["id"]: c for c in orig.get("criteria", [])}
    nb = {c["id"]: c for c in new.get("criteria", [])}
    preserved = all(nb.get(i, {}).get("source_claim") == c.get("source_claim")
                    for i, c in ob.items())
    if defect == "one_sided":
        addressed = all(_has_ceiling(nb.get(t, {})) for t in targets)
    else:
        addressed = all(
            nb.get(t, {}).get("check") != ob.get(t, {}).get("check")
            or nb.get(t, {}).get("params") != ob.get(t, {}).get("params")
            for t in targets)
    return {"lint_pass": not hard, "source_claims_preserved": preserved,
            "defect_addressed": addressed,
            "n_criteria": len(new.get("criteria", []))}


def _discover(base):
    seen = {}
    for rep in sorted(Path(base).glob("run_*/sessions/*/fly_report.json")):
        try:
            r = json.loads(rep.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if r.get("status") != "escalated":
            continue
        if not (r.get("rework") or {}).get("directives"):
            continue
        name = r.get("scenario") or rep.parent.name
        seen[name] = rep.parent  # later run wins
    return [seen[k] for k in sorted(seen)]


def _run_arm(arm, client, story, doc, claims, verdict, evidence, defect):
    if arm == "classic":
        new_doc, ok = redraft_criteria(client, story, doc, claims, "",
                                       verdict["guidance"],
                                       log_fn=lambda *a, **k: None)
        return new_doc, {"applied": bool(ok)}
    new_doc, ok, directive = dr.defect_response(client, verdict, evidence,
                                                doc, log_fn=lambda *a, **k: None)
    return new_doc, {"applied": bool(ok), "resolver": directive.get("resolver")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="experiments/fly_benchmark")
    ap.add_argument("--out", default="experiments/fixer_ab")
    ap.add_argument("--llm-config", default=None)
    ap.add_argument("--arms", choices=("both", "classic", "defect"),
                    default="both")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    sessions = _discover(args.base)
    print(f"replayable failures: {len(sessions)}")

    rows = []
    for sd in sessions:
        story, doc, rep, claims = _load_session(sd)
        verdict, evidence = _last_verdict(rep)
        if verdict is None:
            continue
        defect = dr.classify_defect(verdict, evidence)
        targets = (verdict.get("scope") or []) or \
            [c["id"] for c in doc["criteria"]]
        row = {"scenario": rep.get("scenario") or sd.name,
               "session": str(sd), "defect_class": defect, "targets": targets,
               "escalation": rep.get("reason")}
        arms = ("classic", "defect") if args.arms == "both" else (args.arms,)
        for arm in arms:
            client = LLMClient(load_llm_config(args.llm_config))
            t0 = time.time()
            try:
                new_doc, res = _run_arm(arm, client, story, doc, claims,
                                        verdict, evidence, defect)
            except Exception as e:  # noqa: BLE001 - a replay crash is a finding
                new_doc = doc
                res = {"applied": False, "error": f"{type(e).__name__}: {e}"}
            res.update(_measure(doc, new_doc, targets, defect))
            res["elapsed_s"] = round(time.time() - t0, 1)
            res["usage"] = client.usage_totals()
            row[arm] = res
            u = res["usage"]
            print(f"{row['scenario']} [{arm}] defect={defect} "
                  f"applied={res['applied']} lint={res['lint_pass']} "
                  f"preserved={res['source_claims_preserved']} "
                  f"addressed={res['defect_addressed']} "
                  f"tok={u['total_tokens']} prompt_chars={u['prompt_chars']} "
                  f"({res['elapsed_s']}s)", flush=True)
        rows.append(row)

    (out_dir / "ab_fixer.json").write_text(json.dumps(rows, indent=2),
                                           encoding="utf-8")

    def agg(arm):
        rs = [r[arm] for r in rows if arm in r]
        n = len(rs) or 1

        def pct(key):
            return round(100 * sum(1 for r in rs if r.get(key)) / n, 1)

        return {"n": len(rs), "applied_pct": pct("applied"),
                "lint_pass_pct": pct("lint_pass"),
                "preserved_pct": pct("source_claims_preserved"),
                "addressed_pct": pct("defect_addressed"),
                "total_tokens": sum(r["usage"]["total_tokens"] for r in rs),
                "avg_prompt_chars": round(
                    sum(r["usage"]["prompt_chars"] for r in rs) / n)}

    summary = {arm: agg(arm) for arm in ("classic", "defect")
               if args.arms in ("both", arm)}
    (out_dir / "ab_fixer_summary.json").write_text(json.dumps(summary, indent=2),
                                                   encoding="utf-8")
    print("\n=== FIXER A/B SUMMARY ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
