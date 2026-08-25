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


def run_fly(story, client, sessions_dir="sessions", slug=None,
            max_iterations=10, max_llm_proposals=8):
    """Fly one story end-to-end without human input. Returns the report.

    The report ALWAYS contains: status ('converged' | 'escalated' |
    'aborted' | ...), reason (for non-landings), session path, and full
    telemetry (every pipeline message + every gate decision taken).
    """
    io = _FlyIO()
    try:
        result = run_new_story(client, story, io, sessions_dir=sessions_dir,
                               slug=slug or "fly",
                               max_iterations=max_iterations,
                               max_llm_proposals=max_llm_proposals)
    except Exception as e:  # noqa: BLE001 - the harness must ALWAYS emit a
        # report; a crash mid-flight is itself a finding for maintenance
        result = {"status": "error", "reason": f"{type(e).__name__}: {e}",
                  "session": None}

    report = {
        "status": result.get("status"),
        "reason": result.get("reason"),
        "detail": result.get("detail"),
        "session": result.get("session"),
        "iterations": result.get("iterations"),
        "llm_proposals": result.get("llm_proposals"),
        "thin_margins": result.get("thin_margins"),
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
    return {
        "stories": len(reports),
        "landed": len(landed),
        "unassisted_landing_rate_pct": round(len(landed) / n * 100, 1),
        "escalated": len(escalated),
        "escalation_reasons": sorted({r.get("reason") or "?" for r in escalated}),
        "other": [r.get("status") for r in reports
                  if r.get("status") not in ("converged", "escalated")],
    }
