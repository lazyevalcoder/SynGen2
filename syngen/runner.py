"""Flight runner: stage-based execution with resume and bounded rewind (P12).

A flight is 7 stages (see `syngen.stages`). This module owns the progress
state (`flight_state.json` in the session folder) and the execution loop:

- `run_stages(session, ..., upto=N)`  - run up to and including stage N;
- `run_stages(..., only=N)`           - run exactly stage N;
- `run_stages(..., from_stage=N)`     - rewind to N and run forward;
- no bound                            - resume at the next incomplete stage;
- on escalation, attribute the failure to an upstream stage and re-run from
  there (bounded by `max_rewind_rounds`), then stop with the reason.

Legacy sessions (no `flight_state.json`) get their state inferred from the
artifacts on disk.
"""
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from syngen.stages import STAGE_NAMES, STAGES, StageContext
from syngen.usage import render_usage, write_usage

STATE_FILE = "flight_state.json"
STATE_SCHEMA = 1

DEFAULT_FLAGS = {
    "stage23": "classic",
    "use_capability": False,
    "rework_strategy": "classic",
    "use_critic": True,
    "use_personas": False,
    "max_rework_rounds": 2,
    "max_iterations": 10,
    "max_llm_proposals": 8,
}

# Deterministic stage attribution for an escalation kind. `convergence` is
# genuinely ambiguous and falls back to the rework judge.
_REWIND = {
    "criteria_coverage": 2,
    "criteria_consistency": 2,
    "criteria_geometry": 2,
    "criteria_menu": 2,
    "criteria_intent": 2,
    "draft_invalid": 3,
    "stage3_buildability": 3,
    "preflight_structural": 3,
    "preflight_calibration": 4,
    "preflight_persist": 4,
    "structure": 5,
}

_ARTIFACTS = ("criteria.json", "simulator.json", "convergence_summary.json",
              "validation_report.md")


@dataclass
class FlightState:
    root: Path
    data: dict = field(default_factory=dict)

    @property
    def path(self):
        return self.root / STATE_FILE

    @classmethod
    def load(cls, session):
        state = cls(session.root)
        if state.path.exists():
            state.data = json.loads(state.path.read_text(encoding="utf-8"))
            state.data.setdefault("flags", dict(DEFAULT_FLAGS))
        else:
            state.data = cls._infer(session.root)
            state.save()
        return state

    @staticmethod
    def _infer(root):
        stages = {}

        def done(n, artifact):
            stages[str(n)] = {"status": "completed", "artifact": artifact,
                              "inferred": True}

        if (root / "computable_claims.json").exists():
            done(1, "computable_claims.json")
        if (root / "criteria.json").exists():
            done(2, "criteria.json")
        if (root / "simulator.json").exists():
            done(3, "simulator.json")
        # Pre-flight leaves no artifact of its own; convergence implies it ran.
        if (root / "history").is_dir():
            stages[str(4)] = {"status": "completed", "inferred": True}
            stages[str(5)] = {"status": "completed", "inferred": True}
        if (root / "validation_report.md").exists():
            done(6, "validation_report.md")
        nxt = 1
        while nxt <= 7 and stages.get(str(nxt), {}).get("status") == "completed":
            nxt += 1
        return {
            "schema": STATE_SCHEMA,
            "flags": dict(DEFAULT_FLAGS),
            "stages": stages,
            "next_stage": nxt,
            "status": "in_progress" if nxt <= 7 else "converged",
            "rewind_to": None,
            "attempts": {},
        }

    def save(self):
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    # -- stage bookkeeping --------------------------------------------------

    def status_of(self, n):
        return self.data["stages"].get(str(n), {}).get("status", "pending")

    def set_stage(self, n, status, artifacts=None, reason=""):
        entry = self.data["stages"].setdefault(str(n), {})
        entry["status"] = status
        if reason:
            entry["reason"] = reason
        if artifacts:
            entry["artifact"] = artifacts[-1]
            entry["artifacts"] = artifacts
        if status == "completed":
            from datetime import datetime
            entry["at"] = datetime.now().isoformat(timespec="seconds")
            self.data["next_stage"] = n + 1
        self.save()

    def mark_stale_from(self, n):
        """Downstream artifacts are invalid once stage n is re-run."""
        for i in range(n, 8):
            st = self.status_of(i)
            if st in ("completed", "stale", "escalated", "aborted"):
                self.data["stages"][str(i)] = {"status": "stale"}
        self.data["next_stage"] = min(self.data.get("next_stage", 8), n)
        self.save()

    def next_stage(self):
        n = 1
        while n <= 7 and self.status_of(n) == "completed":
            n += 1
        return n

    def table(self):
        rows = []
        for n in range(1, 8):
            st = self.status_of(n)
            mark = "next" if n == self.next_stage() else ""
            rows.append((n, STAGE_NAMES[n], st, mark))
        return rows


def _archive(session, stage):
    """Keep the pre-rewind artifacts for replay before they are overwritten."""
    hist = session.root / "history"
    hist.mkdir(exist_ok=True)
    k = 1
    while (hist / f"stage{stage:02d}_attempt{k}").exists():
        k += 1
    dest = hist / f"stage{stage:02d}_attempt{k}"
    dest.mkdir()
    for name in _ARTIFACTS:
        src = session.root / name
        if src.exists():
            shutil.copy2(src, dest / name)


def _judge_rewind(client, session, story, evidence, round_no, log):
    """Ask the rework judge where an ambiguous failure belongs."""
    from syngen.phases.rework import judge_revision
    doc_path = session.root / "criteria.json"
    doc = (json.loads(doc_path.read_text(encoding="utf-8"))
           if doc_path.exists() else {"criteria": []})
    verdict = judge_revision(client, story, evidence, doc, round_no,
                             log_fn=log)
    if verdict["action"] == "rework_criteria":
        return 2, verdict["guidance"]
    if verdict["action"] == "rework_config":
        return 3, verdict["guidance"]
    return None, ""


def rewind_target(evidence):
    if not evidence:
        return None
    return _REWIND.get(evidence.get("kind"))


def run_stages(session, client, io, story=None, *, upto=None, only=None,
               from_stage=None, all=False, flags=None, auto_rewind=True,
               max_rewind_rounds=2):
    """Execute the flight stage by stage. Returns a result dict."""
    state = FlightState.load(session)
    if flags:
        state.data["flags"] = {**state.data.get("flags", {}), **flags}
    f = state.data["flags"]
    if story is None:
        story = session.latest_story()
    log = io.inform

    def _finish(result):
        u = write_usage(session, client)
        result["llm_usage"] = u
        log(render_usage(u))
        return result

    # --- decide the window ---
    if only is not None:
        start = stop = int(only)
        state.mark_stale_from(start + 1)
    elif from_stage is not None:
        start = int(from_stage)
        stop = int(upto) if upto else 7
        state.mark_stale_from(start)
    else:
        start = state.next_stage()
        stop = int(upto) if upto else 7
        if all:
            stop = 7
    if start > 7:
        state.data["status"] = "converged"
        state.save()
        return _finish({"status": "converged", "session": str(session.root),
                        "next_stage": 8,
                        "rework": {"rounds": 0, "directives": []}})

    directives = []
    rewind_rounds = 0
    last = None
    n = start
    while n <= stop:
        name, fn = STAGES[n]
        state.data["current_stage"] = n
        state.data["status"] = "in_progress"
        state.save()
        log(f"\n===== Stage {n}/7: {name} =====")
        ctx = StageContext(session=session, client=client, io=io, story=story,
                           log=log, flags=f,
                           guidance=state.data.get("guidance", ""))
        try:
            result = fn(ctx)
        except Exception as e:  # noqa: BLE001 - a stage crash must escalate,
            # not lose the flight (and must still capture usage, P15)
            from syngen.stages import StageResult
            log(f"Stage {n} ({name}) raised {type(e).__name__}: {e}")
            session.log(f"STAGE {n} ERROR: {type(e).__name__}: {e}")
            result = StageResult(n, "escalated", reason="stage_error",
                                 detail=f"{type(e).__name__}: {e}")
        last = result
        if result.status == "completed":
            state.data.pop("guidance", None)
            state.set_stage(n, "completed", artifacts=result.artifacts)
            n += 1
            continue

        # --- non-completion: attribute and possibly rewind ---
        state.set_stage(n, result.status, reason=result.reason)
        target = result.rewind_to
        guidance = ""
        if target is None:
            target = rewind_target(result.evidence)
        if target is None and result.evidence:
            target, guidance = _judge_rewind(client, session, story,
                                             result.evidence,
                                             len(directives) + 1, log)
        directives.append({
            "stage": n, "escalation": result.reason,
            "rewind_to": target, "status": result.status,
            "reason": result.reason})
        state.data["rewind_to"] = target
        if guidance:
            state.data["guidance"] = guidance
        state.save()

        if (auto_rewind and target is not None and target <= n
                and rewind_rounds < max_rewind_rounds):
            rewind_rounds += 1
            _archive(session, target)
            state.mark_stale_from(target)
            kind = "retry" if target == n else "rewind"
            log(f"{kind.capitalize()}: stage {n} ({result.reason}) -> "
                f"re-running from stage {target} "
                f"(round {rewind_rounds}/{max_rewind_rounds}).")
            n = target
            continue

        state.data["status"] = result.status
        state.save()
        return _finish({
            "status": "converged" if result.status == "completed" else
                      ("aborted" if result.status == "aborted" else "escalated"),
            "reason": result.reason,
            "session": str(session.root),
            "next_stage": state.next_stage(),
            "stages": [list(r) for r in state.table()],
            "rework": {"rounds": rewind_rounds, "directives": directives},
        })

    state.data["status"] = "converged" if state.next_stage() > 7 else "in_progress"
    state.data["current_stage"] = None
    state.save()
    return _finish({
        "status": state.data["status"],
        "session": str(session.root),
        "next_stage": state.next_stage(),
        "stages": [list(r) for r in state.table()],
        "rework": {"rounds": rewind_rounds, "directives": directives},
    })


def status_rows(session):
    return FlightState.load(session).table()


def create_session_and_run(story, client, io, sessions_dir="sessions", slug=None,
                           **kwargs):
    """Create a fresh session, save the story, then run the stage runner."""
    from syngen.session import Session
    session = Session.create(sessions_dir, slug=slug or story[:40])
    session.save_story(story)
    return run_stages(session, client, io, story, **kwargs)
