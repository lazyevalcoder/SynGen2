"""M6 P3 infra fixes regression tests.

F8.1 sigma-less deal_size_lognormal: contract-checked early, deterministic
default in preflight instead of a raw KeyError deep in flight.
F8.2 crash-path fly reports keep the session reference.
F5.3 coverage-guard escalations persist the rejected criteria draft.
"""
import json
from pathlib import Path

import pytest

from syngen.config import ConfigError, validate_simulator_doc
from syngen.llm.client import FakeLLM, LLMResponse
from syngen.phases.preflight import autocalibrate, calibrate


def llm_json(obj):
    return LLMResponse(content=json.dumps(obj))


BASE_CFG = {
    "seed": 7,
    "time_model": {
        "fiscal_year": "FY26",
        "quarter_labels": ["FY26-Q1", "FY26-Q2"],
        "quarter_end_dates": ["2026-03-31", "2026-06-30"],
    },
    "output": {"workbook": "out.xlsx"},
    "accounts": {
        "count": 40,
        "regions": {"AMER": 0.6, "EMEA": 0.4},
        "segments": {"Enterprise": 0.5, "SMB": 0.5},
        "industries": ["Software", "Retail"],
    },
    "opportunities": {
        "per_quarter": 30,
        "win_rate": 0.3,
        "win_rate_jitter": 0.005,
        "owners": ["A Rep", "B Rep"],
        "deal_duration_days": {"means": [40, 40]},
        "close_clustering": {
            "end_of_quarter_window_days": 10,
            "share_in_end_of_quarter_window": 0.3,
        },
        "deal_size_lognormal": {"median_usd": 40000},
        "discount": {
            "base_by_quarter": {"AMER": [10.0, 10.0], "EMEA": [10.0, 10.0]},
            "noise_sd_pp": 2,
            "end_of_quarter_boost_pp": 4,
            "end_of_quarter_window_days": 10,
            "min_pct": 0, "max_pct": 40,
        },
    },
}


# --- F8.1 ---------------------------------------------------------------------


def test_schema_rejects_sigmaless_block_with_clear_message():
    with pytest.raises(ConfigError, match="sigma is required"):
        validate_simulator_doc(json.loads(json.dumps(BASE_CFG)))


def test_schema_rejects_out_of_range_sigma():
    cfg = json.loads(json.dumps(BASE_CFG))
    cfg["opportunities"]["deal_size_lognormal"]["sigma"] = 9.0
    with pytest.raises(ConfigError, match="must be in"):
        validate_simulator_doc(cfg)


def test_calibrate_defaults_sigma_with_soft_finding():
    cfg = json.loads(json.dumps(BASE_CFG))
    findings = calibrate(cfg, {"criteria": []})
    assert cfg["opportunities"]["deal_size_lognormal"]["sigma"] == 0.6
    soft = [f for f in findings if f["rule"] == "PF1"]
    assert soft and "0.6" in soft[0]["msg"]
    assert not [f for f in findings if f["rule"] == "PF0"]


def test_autocalibrate_defaults_sigma_as_fix_entry():
    cfg = json.loads(json.dumps(BASE_CFG))
    fixes = autocalibrate(cfg, {"criteria": []})
    assert any("sigma" in f and "0.6" in f for f in fixes)
    assert cfg["opportunities"]["deal_size_lognormal"]["sigma"] == 0.6


def test_present_sigma_is_untouched():
    cfg = json.loads(json.dumps(BASE_CFG))
    cfg["opportunities"]["deal_size_lognormal"]["sigma"] = 0.55
    calibrate(cfg, {"criteria": []})
    assert cfg["opportunities"]["deal_size_lognormal"]["sigma"] == 0.55


# --- F8.2 ---------------------------------------------------------------------


def test_fly_crash_keeps_session_reference(tmp_path):
    from syngen.fly import run_fly

    class Boom:
        def chat(self, *a, **k):  # first LLM call explodes mid-flight
            raise RuntimeError("endpoint vanished")

    report = run_fly("A story about discounts eroding margins.", Boom(),
                     sessions_dir=str(tmp_path), slug="crash")
    assert report["status"] == "error"
    assert "RuntimeError" in (report["reason"] or "")
    assert report["session"], "crash report must keep the session folder"
    assert Path(report["session"]).is_dir()
    assert (Path(report["session"]) / "fly_report.json").exists()


# --- F5.3 ---------------------------------------------------------------------


def test_guard_escalation_persists_criteria_draft(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from test_pipeline import PRECHECK, SilentIO
    from syngen.pipeline import run_new_story

    generic_only = {"definitions": {}, "criteria": [
        {"id": "AC1", "name": "sanity", "check": "data_sanity",
         "params": {}, "source_claim": "realism"}]}
    off_target = {"definitions": {}, "criteria": [
        {"id": "AC1", "name": "win rate", "check": "win_rate_flat",
         "params": {"band_pp": 10}, "source_claim": "narrative"}]}
    uncovered = llm_json({"uncovered": [
        {"claim": "c", "classification": "VOCAB_GAP",
         "existing_check": None, "reason": "r"}],
        "covered": []})
    client = FakeLLM([
        llm_json(PRECHECK),
        llm_json(generic_only),
        llm_json(off_target),
        uncovered,
    ])
    result = run_new_story(client, "Unowned accounts ballooned in H2.",
                           SilentIO(), sessions_dir="sessions", slug="f53")
    assert result["status"] == "escalated"
    persisted = Path(result["session"]) / "criteria.json"
    assert persisted.exists()
    saved = json.loads(persisted.read_text(encoding="utf-8"))
    assert {c["check"] for c in saved["criteria"]} == {"win_rate_flat"}
