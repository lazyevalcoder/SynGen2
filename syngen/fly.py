"""Solo-flight harness (flight model, M5 iter 5): story in, dataset+proof
out, ZERO human interaction - the certification run for "the pilot flies
alone".

`run_fly` drives the full pipeline through an auto-confirming IO shell,
captures every message as telemetry, and writes a structured
fly_report.json into the session folder. The report is the benchmark unit:
status is either a landing (with iteration/proposal counts) or an honest
escalation (classified reason) - never a silent partial result.
"""
import json
import re
from pathlib import Path

from syngen.pipeline import run_new_story


class _FlyIO:
    """Auto-confirming IO shell with full telemetry capture."""

    def __init__(self):
        self.messages = []
        self.decisions = []

    def inform(self, text):
        self.messages.append(str(text))

    def confirm(self, prompt, default=True):
        self.decisions.append({"prompt": prompt, "answer": default})
        return default

    def ask(self, prompt, default=""):
        self.decisions.append({"prompt": prompt, "answer": default})
        return default

    def free_text(self, prompt):
        return ""


def _newest_session(sessions_dir):
    """Newest session folder under sessions_dir (mtime order), if any."""
    base = Path(sessions_dir)
    if not base.is_dir():
        return None
    dirs = [d for d in base.iterdir() if d.is_dir() and
            (d / "session_log.md").exists()]
    return max(dirs, key=lambda d: d.stat().st_mtime) if dirs else None


def _session_for_slug(sessions_dir, slug):
    """The session folder for a specific slug (P10: race-safe under parallel
    runs - distinct scenarios use distinct slugs, unlike newest-mtime)."""
    base = Path(sessions_dir)
    if not base.is_dir() or not slug:
        return None
    want = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")[:40] or "story"
    pat = re.compile(rf"_{re.escape(want)}(_\d+)?$")
    matches = [d for d in base.iterdir()
               if d.is_dir() and (d / "session_log.md").exists()
               and pat.search(d.name)]
    return max(matches, key=lambda d: d.stat().st_mtime) if matches else None


def run_fly(story, client, sessions_dir="sessions", slug=None,
            max_iterations=10, max_llm_proposals=8, use_critic=True,
            max_rework_rounds=2, rework_strategy="classic",
            use_capability=False):
    """Fly one story end-to-end without human input. Returns the report.

    The report ALWAYS contains: status ('converged' | 'escalated' |
    'aborted' | ...), reason (for non-landings), session path, and full
    telemetry (every pipeline message + every gate decision taken).

    max_rework_rounds defaults to 2: the flexible stage-rework loop (P7) -
    an LLM judge routes escalation evidence back to criteria/config drafting
    (bounded, claim-preserving) before the flight ends. A converged report
    carries `rework.rounds` (0 = clean single attempt) so certification can
    tell clean landings from reworked ones.
    """
    io = _FlyIO()
    try:
        result = run_new_story(client, story, io, sessions_dir=sessions_dir,
                               slug=slug or "fly",
                               max_iterations=max_iterations,
                               max_llm_proposals=max_llm_proposals,
                               use_critic=use_critic,
                               max_rework_rounds=max_rework_rounds,
                               rework_strategy=rework_strategy,
                               use_capability=use_capability)
    except Exception as e:  # noqa: BLE001 - the harness must ALWAYS emit a
        # report; a crash mid-flight is itself a finding for maintenance
        # F8.2: the Session is created before any LLM traffic, so even a
        # first-turn crash leaves a folder - infer it instead of losing
        # the session reference (benchmark: scenario_03 report had none).
        inferred = (_session_for_slug(sessions_dir, slug or "fly")
                    or _newest_session(sessions_dir))
        result = {"status": "error", "reason": f"{type(e).__name__}: {e}",
                  "session": str(inferred) if inferred else None}
        if inferred:
            try:
                from syngen.session import Session
                Session.open(inferred).log(
                    f"FLIGHT CRASH: {type(e).__name__}: {e}")
            except Exception:  # noqa: BLE001 - logging must not mask the crash
                pass

    report = {
        "status": result.get("status"),
        "reason": result.get("reason"),
        "detail": result.get("detail"),
        "session": result.get("session"),
        "iterations": result.get("iterations"),
        "llm_proposals": result.get("llm_proposals"),
        "thin_margins": result.get("thin_margins"),
        "loose_margins": result.get("loose_margins"),
        "rework": result.get("rework"),
        "llm_usage": (client.usage_totals()
                      if hasattr(client, "usage_totals") else {}),
        "telemetry": {
            "messages": io.messages,
            "gate_decisions": io.decisions,
        },
    }
    sdir = result.get("session")
    if sdir:
        try:
            (Path(sdir) / "fly_report.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8")
        except OSError:
            pass
    return report


def summarize_reports(reports):
    """Fleet-level view: unassisted landing rate + escalation causes."""
    n = len(reports) or 1
    landed = [r for r in reports if r.get("status") == "converged"]
    escalated = [r for r in reports if r.get("status") == "escalated"]
    usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
             "total_tokens": 0, "elapsed_s": 0.0}
    for r in reports:
        u = r.get("llm_usage") or {}
        for k in usage:
            usage[k] += u.get(k, 0) or 0
    usage["elapsed_s"] = round(usage["elapsed_s"], 2)
    if reports:
        usage["avg_total_tokens_per_flight"] = round(
            usage["total_tokens"] / len(reports), 1)
    return {
        "stories": len(reports),
        "landed": len(landed),
        "unassisted_landing_rate_pct": round(len(landed) / n * 100, 1),
        "escalated": len(escalated),
        "escalation_reasons": sorted({r.get("reason") or "?" for r in escalated}),
        "other": [r.get("status") for r in reports
                  if r.get("status") not in ("converged", "escalated")],
        "llm_usage": usage,
    }
