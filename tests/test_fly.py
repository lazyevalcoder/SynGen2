"""M5 iter 5: syngen fly - the solo-certification harness.

Every flight must end in a structured report: landed (with counts) or an
honest classified escalation - never a crash without a report, never a
silent partial result.
"""
import json

import pytest

from syngen.fly import run_fly, summarize_reports
from test_coverage_guard import GENERIC_ONLY
from test_pipeline import AUDIT_COVERED, BROKEN_SIM, CRITERIA, PRECHECK


def llm_json(obj):
    return LLMResponse(content=json.dumps(obj))


from syngen.llm.client import FakeLLM, LLMResponse  # noqa: E402


def test_fly_lands_and_writes_telemetry_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = FakeLLM([
        llm_json(PRECHECK),
        llm_json(CRITERIA),
        llm_json(AUDIT_COVERED),
        llm_json(BROKEN_SIM),
    ])
    report = run_fly("Q4 discounts deepened, worst in EMEA.", client,
                     sessions_dir="sessions", slug="flyok")
    assert report["status"] == "converged"
    assert report["session"] and report["iterations"] >= 1
    # telemetry captured the whole flight
    assert any("gate 1 passed" in m.lower()
               for m in report["telemetry"]["messages"])
    assert any("deliverables" in m.lower()
               for m in report["telemetry"]["messages"])
    written = json.loads((tmp_path / report["session"] / "fly_report.json")
                         .read_text(encoding="utf-8"))
    assert written["status"] == "converged"


def test_fly_reports_escalation_without_crashing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    uncovered = llm_json({"uncovered": [{"claim": "c", "reason": "r"}],
                          "covered": []})
    client = FakeLLM([
        llm_json(PRECHECK),
        llm_json(GENERIC_ONLY),   # hygiene only -> deterministic gap
        llm_json(GENERIC_ONLY),   # corrective re-draft still vacuous
    ])
    report = run_fly("Unowned accounts ballooned.", client,
                     sessions_dir="sessions", slug="flyneg")
    assert report["status"] == "escalated"
    assert report["reason"] == "criteria_coverage"
    sdir = tmp_path / "sessions"
    reports = list(sdir.glob("*fly*/fly_report.json")) or \
        list(sdir.rglob("fly_report.json"))
    assert reports, "escalated flights must still emit a report"


def test_fly_always_emits_a_report_even_on_crash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    class ExplodingClient(FakeLLM):
        def chat(self, *a, **k):
            raise RuntimeError("endpoint gone")

    report = run_fly("some story", ExplodingClient([]),
                     sessions_dir="sessions", slug="flyboom")
    assert report["status"] == "error"
    assert "RuntimeError" in report["reason"]


def test_summarize_reports_computes_landing_rate():
    reports = [
        {"status": "converged"},
        {"status": "converged"},
        {"status": "escalated", "reason": "structural"},
        {"status": "error"},
    ]
    s = summarize_reports(reports)
    assert s["stories"] == 4
    assert s["landed"] == 2
    assert s["unassisted_landing_rate_pct"] == 50.0
    assert s["escalation_reasons"] == ["structural"]
