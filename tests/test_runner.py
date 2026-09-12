"""P12 flight runner: stage state, resume, rewind, artifact inference."""
import json
from pathlib import Path

import pytest

from syngen.llm.client import FakeLLM, LLMResponse
from syngen.runner import (FlightState, create_session_and_run, rewind_target,
                           run_stages, status_rows)
from syngen.session import Session

from test_pipeline import (AUDIT_COVERED, BROKEN_SIM, CRITERIA, CRITIC_CLEAN,
                           FIX_PROPOSAL, PRECHECK, SilentIO)


def llm_json(obj):
    return LLMResponse(content=json.dumps(obj))


def _full_script():
    return FakeLLM([llm_json(PRECHECK), llm_json(CRITERIA),
                    llm_json(AUDIT_COVERED), llm_json(CRITIC_CLEAN),
                    llm_json(BROKEN_SIM), llm_json(CRITIC_CLEAN),
                    llm_json(FIX_PROPOSAL)])


@pytest.fixture
def run_in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _only_session():
    return next(Path("sessions").iterdir())


def test_stage3_stops_and_reports_next(run_in_tmp):
    result = create_session_and_run(
        "Q4 discounts deepened, worst in EMEA.", _full_script(), SilentIO(),
        sessions_dir="sessions", slug="stage3", upto=3)
    assert result["status"] == "in_progress"
    assert result["next_stage"] == 4
    root = Path(result["session"])
    assert (root / "criteria.json").exists()
    assert (root / "simulator.json").exists()
    assert (root / "decisions.md").exists()
    assert not (root / "validation_report.md").exists()
    assert (root / "flight_state.json").exists()
    state = FlightState.load(Session.open(root))
    assert state.status_of(1) == "completed"
    assert state.status_of(3) == "completed"
    assert state.status_of(4) == "pending"


def test_resume_runs_remaining_stages(run_in_tmp):
    create_session_and_run("story", _full_script(), SilentIO(),
                           sessions_dir="sessions", slug="resume", upto=3)
    session = Session.open(_only_session())
    # Stages 4-7 are deterministic once the config is calibrated: no LLM.
    result = run_stages(session, FakeLLM([]), SilentIO())
    assert result["status"] == "converged"
    assert result["next_stage"] == 8
    assert (session.root / "validation_report.md").exists()
    assert (session.root / "output" / "dataset.xlsx").exists()


def test_status_rows_cover_all_seven(run_in_tmp):
    create_session_and_run("story", _full_script(), SilentIO(),
                           sessions_dir="sessions", slug="status", upto=2)
    session = Session.open(_only_session())
    rows = status_rows(session)
    assert [r[0] for r in rows] == [1, 2, 3, 4, 5, 6, 7]
    assert rows[1][2] == "completed"
    assert any(r[3] == "next" for r in rows)


def test_only_stage_marks_downstream_stale(run_in_tmp):
    create_session_and_run("story", _full_script(), SilentIO(),
                           sessions_dir="sessions", slug="only", upto=7)
    session = Session.open(_only_session())
    assert FlightState.load(session).status_of(7) == "completed"
    client = FakeLLM([llm_json(BROKEN_SIM), llm_json(CRITIC_CLEAN)])
    run_stages(session, client, SilentIO(), only=3)
    state = FlightState.load(session)
    assert state.status_of(3) == "completed"
    assert state.status_of(4) == "stale"
    assert state.next_stage() == 4


def test_from_stage_reruns_forward(run_in_tmp):
    create_session_and_run("story", _full_script(), SilentIO(),
                           sessions_dir="sessions", slug="rewind", upto=7)
    session = Session.open(_only_session())
    result = run_stages(session, FakeLLM([]), SilentIO(), from_stage=4)
    assert result["status"] == "converged"
    assert FlightState.load(session).status_of(4) == "completed"


def test_legacy_session_infers_state(run_in_tmp):
    s = Session.create("sessions", slug="legacy")
    s.save_story("story")
    (s.root / "computable_claims.json").write_text("{}", encoding="utf-8")
    (s.root / "criteria.json").write_text(
        '{"definitions": {}, "criteria": []}', encoding="utf-8")
    (s.root / "simulator.json").write_text("{}", encoding="utf-8")
    state = FlightState.load(s)
    assert state.status_of(1) == "completed"
    assert state.status_of(2) == "completed"
    assert state.status_of(3) == "completed"
    assert state.next_stage() == 4


def test_rewind_target_mapping():
    assert rewind_target({"kind": "criteria_geometry"}) == 2
    assert rewind_target({"kind": "draft_invalid"}) == 3
    assert rewind_target({"kind": "preflight_calibration"}) == 4
    assert rewind_target({"kind": "structure"}) == 5
    assert rewind_target({"kind": "convergence"}) is None


def test_auto_rewind_reruns_upstream(run_in_tmp, monkeypatch):
    from syngen import runner, stages

    calls = []

    def make(n, escalate_first=False, target=None):
        def fn(ctx):
            calls.append(n)
            if escalate_first and calls.count(n) == 1:
                return stages.StageResult(
                    n, "escalated", reason="stuck",
                    evidence={"kind": "criteria_geometry"}, rewind_to=target)
            return stages.StageResult(n, "completed")
        return fn

    for i in (2, 3, 4):
        monkeypatch.setitem(stages.STAGES, i, (stages.STAGE_NAMES[i], make(i)))
    monkeypatch.setitem(stages.STAGES, 5,
                        ("converge", make(5, escalate_first=True, target=2)))
    s = Session.create("sessions", slug="rw")
    s.save_story("story")
    runner.FlightState.load(s).set_stage(1, "completed")
    result = runner.run_stages(s, FakeLLM([]), SilentIO(), from_stage=2,
                               upto=5, max_rewind_rounds=1)
    assert result["status"] == "in_progress"       # stopped at the bound
    assert result["next_stage"] == 6
    assert calls == [2, 3, 4, 5, 2, 3, 4, 5]


def test_auto_rewind_is_bounded(run_in_tmp, monkeypatch):
    from syngen import runner, stages

    calls = []

    def ok(n):
        def fn(ctx):
            calls.append(n)
            return stages.StageResult(n, "completed")
        return fn

    def fail5(ctx):
        calls.append(5)
        return stages.StageResult(5, "escalated", reason="stuck",
                                  evidence={"kind": "criteria_geometry"},
                                  rewind_to=2)

    for i in (2, 3, 4):
        monkeypatch.setitem(stages.STAGES, i, (stages.STAGE_NAMES[i], ok(i)))
    monkeypatch.setitem(stages.STAGES, 5, ("converge", fail5))
    s = Session.create("sessions", slug="rw2")
    s.save_story("story")
    result = runner.run_stages(s, FakeLLM([]), SilentIO(), from_stage=2,
                               upto=5, max_rewind_rounds=1)
    assert result["status"] == "escalated"
    # one initial pass + one bounded rewind, then stop
    assert calls == [2, 3, 4, 5, 2, 3, 4, 5]


def test_stage_sugar_normalizes_argv():
    from syngen.__main__ import _normalize_argv
    assert _normalize_argv(["run", "s", "--stage-3"]) == \
        ["run", "s", "--stage", "3"]
    assert _normalize_argv(["run", "s", "--all"]) == ["run", "s", "--all"]


def test_cli_status_prints_progress(run_in_tmp, capsys):
    from syngen.__main__ import main
    create_session_and_run("story", _full_script(), SilentIO(),
                           sessions_dir="sessions", slug="cli", upto=3)
    root = str(_only_session())
    assert main(["status", root]) == 0
    out = capsys.readouterr().out
    assert "criteria" in out and "config" in out
    assert "completed" in out and "next" in out


def test_stage_histogram_counts_failures():
    from syngen.fly import stage_histogram
    reports = [
        {"status": "converged",
         "stages": [[1, "intake", "completed", ""],
                    [2, "criteria", "completed", ""],
                    [3, "config", "completed", ""]]},
        {"status": "escalated", "next_stage": 3,
         "stages": [[1, "intake", "completed", ""],
                    [2, "criteria", "completed", ""],
                    [3, "config", "escalated", ""]]},
    ]
    h = stage_histogram(reports)
    # converged reached stage 3; the escalated one completed only through 2
    assert h["stage_reached"] == {2: 1, 3: 1}
    assert h["escalations_by_stage"] == {3: 1}


def test_same_stage_failure_is_retried(run_in_tmp, monkeypatch):
    """P17: a stage that fails and points at ITSELF is retried (bounded),
    instead of being terminal."""
    from syngen import runner, stages

    calls = []

    def make(n, fail_first=False):
        def fn(ctx):
            calls.append(n)
            if fail_first and calls.count(n) == 1:
                return stages.StageResult(
                    n, "escalated", reason="draft_invalid",
                    evidence={"kind": "draft_invalid"}, rewind_to=n)
            return stages.StageResult(n, "completed")
        return fn

    for i in (2, 4, 5):
        monkeypatch.setitem(stages.STAGES, i, (stages.STAGE_NAMES[i], make(i)))
    monkeypatch.setitem(stages.STAGES, 3,
                        (stages.STAGE_NAMES[3], make(3, fail_first=True)))
    s = Session.create("sessions", slug="retry")
    s.save_story("story")
    runner.FlightState.load(s).set_stage(1, "completed")
    result = runner.run_stages(s, FakeLLM([]), SilentIO(), from_stage=2,
                               upto=5, max_rewind_rounds=1)
    assert result["status"] == "in_progress"
    assert calls == [2, 3, 3, 4, 5]


def test_usage_written_to_session(run_in_tmp):
    """P15: the runner persists per-flight LLM usage (calls/tokens)."""
    result = create_session_and_run("story", _full_script(), SilentIO(),
                                    sessions_dir="sessions", slug="usage",
                                    upto=3)
    session = Session.open(_only_session())
    assert (session.root / "usage.json").exists()
    u = json.loads((session.root / "usage.json").read_text(encoding="utf-8"))
    assert u["calls"] >= 1
    assert result["llm_usage"]["calls"] >= 1
