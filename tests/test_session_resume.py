"""M3: session persistence (contracts section 8) + resume/tweak flows."""
import json
from pathlib import Path

import pytest

from syngen.llm.client import FakeLLM, LLMResponse
from syngen.pipeline import run_new_story, run_resume
from syngen.session import Session, SessionError

from test_pipeline import (
    BROKEN_SIM,
    CRITERIA,
    CRITIC_CLEAN,
    PERSONAS,
    PRECHECK,
    FIX_PROPOSAL,
    AUDIT_COVERED,
    SilentIO,
    make_fake_client,
)


def llm_json(obj):
    return LLMResponse(content=json.dumps(obj))


import pytest  # noqa: E402


@pytest.fixture
def run_in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _create_converged_session(run_in_tmp):
    result = run_new_story(
        FakeLLM([llm_json(PRECHECK), llm_json(CRITERIA),
                 llm_json(AUDIT_COVERED), llm_json(CRITIC_CLEAN),
                 llm_json(BROKEN_SIM), llm_json(CRITIC_CLEAN),
                 llm_json(FIX_PROPOSAL)]),
        "Q4 discounts deepened, worst in EMEA.",
        SilentIO(), sessions_dir="sessions", slug="resume")
    assert result["status"] == "converged"
    return result["session"]


# --- session unit behavior ---------------------------------------------------

def test_story_versioning_and_mirror(run_in_tmp):
    s = Session.create("sessions", slug="ver")
    assert s.save_story("first") == 1
    assert s.save_story("second") == 2
    assert s.latest_story() == "second"
    assert len(s.story_versions()) == 2
    assert (s.root / "story.md").read_text(encoding="utf-8") == "second"


def test_latest_story_legacy_layout(run_in_tmp):
    s = Session.create("sessions", slug="legacy")
    (s.root / "story.md").write_text("legacy text", encoding="utf-8")
    assert s.latest_story() == "legacy text"


def test_open_rejects_non_sessions(tmp_path):
    bogus = tmp_path / "not_a_session"
    bogus.mkdir()
    with pytest.raises(SessionError, match="missing session_log"):
        Session.open(bogus)
    with pytest.raises(SessionError, match="no such session"):
        Session.open(tmp_path / "does_not_exist")


def test_list_all_reports_ready_and_incomplete(run_in_tmp):
    _create_converged_session(run_in_tmp)
    stray = Session.create("sessions", slug="stray")
    found = Session.list_all("sessions")
    names = [p.name for p in found]
    assert any("resume" in n and "[state]" not in n for n in names)
    states = {p.name: ((p / "criteria.json").exists() and
                       (p / "simulator.json").exists()) for p in found}
    ready = [n for n, ok in states.items() if ok]
    incomplete = [n for n, ok in states.items() if not ok]
    assert any("resume" in n for n in ready)
    assert any("stray" in n for n in incomplete)


# --- resume flows -------------------------------------------------------------

def test_history_archive_written_per_iteration(run_in_tmp):
    root = Path(_create_converged_session(run_in_tmp))
    hist = list((root / "history").glob("iter*_simulator.json"))
    reports = list((root / "history").glob("iter*_validation_report.json"))
    assert len(hist) >= 1 and len(reports) == len(hist)
    # archived config matches what produced iteration 1
    archived = json.loads(hist[0].read_text(encoding="utf-8"))
    assert archived["seed"] == BROKEN_SIM["seed"]


def test_resume_without_story_regenerates(run_in_tmp):
    root = _create_converged_session(run_in_tmp)
    result = run_resume(root, FakeLLM([]), SilentIO())
    assert result["status"] == "converged"
    assert result["iterations"] == 1, "converged config must land immediately"
    assert result["llm_proposals"] == 0


def test_resume_parametric_amends_criteria_and_reconverges(run_in_tmp):
    root = _create_converged_session(run_in_tmp)
    classification = {
        "route": "parametric",
        "changed_claims": ["Q1 discount target moved to 13%"],
        "proposed_criteria_amendments": [
            {"id": "AC2", "param": "target_pct", "to": 13}],
        "proposed_config_edits": [],
    }
    result = run_resume(root, FakeLLM([llm_json(classification)]),
                        SilentIO(), new_story="Q1 discounts settled near 13%.")
    assert result["status"] == "converged"

    doc = json.loads((Path(root) / "criteria.json").read_text(encoding="utf-8"))
    ac2 = next(c for c in doc["criteria"] if c["id"] == "AC2")
    assert ac2["params"]["target_pct"] == 13
    log_text = (Path(root) / "session_log.md").read_text(encoding="utf-8")
    assert "GATE 1 re-approval passed after amendment." in log_text


def test_resume_parametric_surfaces_dependency_closure(run_in_tmp):
    """An amendment to AC2 must surface criteria that depend on AC2 before
    re-approval - here AC5 is given a depends_on edge on AC2."""
    root = _create_converged_session(run_in_tmp)
    crit_path = Path(root) / "criteria.json"
    doc = json.loads(crit_path.read_text(encoding="utf-8"))
    ac5 = next(c for c in doc["criteria"] if c["id"] == "AC5")
    ac5["depends_on"] = ["AC2"]
    crit_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    io_messages = []
    io = SilentIO()
    orig_inform = io.inform
    io.inform = lambda text: (io_messages.append(str(text)),
                              orig_inform(text))

    classification = {
        "route": "parametric",
        "changed_claims": ["target tweak"],
        "proposed_criteria_amendments": [
            {"id": "AC2", "param": "tolerance_pp", "to": 5}],
        "proposed_config_edits": [],
    }
    result = run_resume(root, FakeLLM([llm_json(classification)]),
                        io, new_story="slightly different tolerance.")
    assert result["status"] == "converged"
    joined = "\n".join(io_messages)
    assert "Dependency propagation" in joined
    assert "AC5" in joined


def test_resume_taxonomy_edits_segments_and_renormalizes(run_in_tmp):
    root = _create_converged_session(run_in_tmp)
    classification = {
        "route": "taxonomy",
        "changed_claims": ["CSB segment added"],
        "proposed_criteria_amendments": [],
        "proposed_config_edits": [
            {"path": "accounts.segments.CSB", "value": 0.1}],
    }
    result = run_resume(root, FakeLLM([llm_json(classification)]),
                        SilentIO(), new_story="Include our CSB segment too.")
    assert result["status"] == "converged"

    cfg = json.loads((Path(root) / "simulator.json").read_text(encoding="utf-8"))
    segments = cfg["accounts"]["segments"]
    assert "CSB" in segments
    assert abs(sum(segments.values()) - 1.0) < 1e-6


def test_resume_taxonomy_container_replacement_rejected(run_in_tmp):
    """Live-run-1 regression: classifier replaced the whole segments dict
    with a list. The applier must reject it instead of corrupting config."""
    root = _create_converged_session(run_in_tmp)
    classification = {
        "route": "taxonomy",
        "changed_claims": ["add CSB"],
        "proposed_criteria_amendments": [],
        "proposed_config_edits": [
            {"path": "accounts.segments",
             "value": ["SMB", "Mid-Market", "Enterprise", "CSB"]}],
    }
    result = run_resume(root, FakeLLM([llm_json(classification)]),
                        SilentIO(),
                        new_story="Include CSB in the segment mix.")
    assert result["status"] == "aborted"

    cfg = json.loads((Path(root) / "simulator.json").read_text(
        encoding="utf-8"))
    assert isinstance(cfg["accounts"]["segments"], dict), \
        "container must survive a bad proposal untouched"


def test_resume_taxonomy_rename_rejected(run_in_tmp):
    """Live-M3 lesson #2: a container replacement that renames existing
    values (Enterprise -> ENT) must be rejected, not silently applied."""
    root = _create_converged_session(run_in_tmp)
    classification = {
        "route": "taxonomy",
        "changed_claims": ["add CSB"],
        "proposed_criteria_amendments": [],
        "proposed_config_edits": [
            {"path": "accounts.segments",
             "value": {"SMB": 0.35, "MID": 0.3, "ENT": 0.25, "CSB": 0.1}}],
    }
    result = run_resume(root, FakeLLM([llm_json(classification)]),
                        SilentIO(),
                        new_story="Add CSB to the segment mix.")
    assert result["status"] == "aborted"

    cfg = json.loads((Path(root) / "simulator.json").read_text(
        encoding="utf-8"))
    segments = cfg["accounts"]["segments"]
    assert set(segments) == {"Enterprise", "Mid-Market", "SMB"}, \
        "original values must survive; no silent renames"


def test_resume_taxonomy_container_addition_accepted(run_in_tmp):
    """Container replacement that only ADDS values is legitimate."""
    root = _create_converged_session(run_in_tmp)
    classification = {
        "route": "taxonomy",
        "changed_claims": ["add CSB"],
        "proposed_criteria_amendments": [],
        "proposed_config_edits": [
            {"path": "accounts.segments",
             "value": {"Enterprise": 0.27, "Mid-Market": 0.36,
                       "SMB": 0.27, "CSB": 0.10}}],
    }
    result = run_resume(root, FakeLLM([llm_json(classification)]),
                        SilentIO(),
                        new_story="Add CSB to the segment mix.")
    assert result["status"] == "converged"
    cfg = json.loads((Path(root) / "simulator.json").read_text(
        encoding="utf-8"))
    segments = cfg["accounts"]["segments"]
    assert set(segments) == {"Enterprise", "Mid-Market", "SMB", "CSB"}
    assert abs(sum(segments.values()) - 1.0) < 1e-9


def test_resume_structural_change_escalates_with_message(run_in_tmp):
    root = _create_converged_session(run_in_tmp)
    classification = {
        "route": "structural",
        "changed_claims": ["track pipeline stages separately"],
        "notes": "requires open-pipeline state machine",
        "proposed_criteria_amendments": [],
        "proposed_config_edits": [],
    }
    messages = []

    class CapturingIO(SilentIO):
        def inform(self, text):
            messages.append(str(text))

    result = run_resume(root, FakeLLM([llm_json(classification)]),
                        CapturingIO(), new_story="Track open deals by stage.")
    assert result["status"] == "escalated"
    assert result["reason"] == "structural"
    assert any("STRUCTURAL CHANGE" in m for m in messages)


def test_resume_guardrail_failure_treated_as_structural(run_in_tmp):
    """Classifier claims parametric but proposes a config edit: the
    deterministic guardrails override the route (GAPS G11 defense)."""
    root = _create_converged_session(run_in_tmp)
    classification = {
        "route": "parametric",
        "changed_claims": ["add CSB"],
        "proposed_criteria_amendments": [],
        "proposed_config_edits": [
            {"path": "accounts.segments.CSB", "value": 0.1}],
    }
    messages = []

    class CapturingIO(SilentIO):
        def inform(self, text):
            messages.append(str(text))

    result = run_resume(root, FakeLLM([llm_json(classification)]),
                        CapturingIO(), new_story="Add CSB segment.")
    assert result["status"] == "escalated"
    assert result["reason"] == "structural"


def test_resume_identical_story_short_circuits_no_llm(run_in_tmp):
    """Live-M3 lesson: resubmitting the same text must not burn an LLM call
    or create a redundant story version."""
    root = _create_converged_session(run_in_tmp)
    same_text = (Path(root) / "story.v1.md").read_text(encoding="utf-8")
    n_before = len(list(Path(root).glob("story.v*.md")))
    result = run_resume(root, FakeLLM([]), SilentIO(), new_story=same_text)
    assert result["status"] == "converged"
    assert len(list(Path(root).glob("story.v*.md"))) == n_before


def test_resume_invalid_session_rejected(run_in_tmp):
    with pytest.raises(SessionError, match="no such session"):
        run_resume("sessions/__nope__", FakeLLM([]), SilentIO(),
                   new_story=None)
