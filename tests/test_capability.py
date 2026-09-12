"""Capability service + stage-2/3 workbench: the drafter's tools.

- capability_sheet: compact numeric context (replaces the rulebook).
- assess_criteria / assess_config: reachability + the gap.
- snap_criteria: deterministic clamp into the envelope.
- _capability_workbench: bounded (never loops).
"""
import copy

from syngen.capability import (assess_config, assess_criteria,
                               capability_sheet, snap_criteria)
from syngen.llm.client import FakeLLM

from test_entity_schemas import ALL_BLOCKS_CFG
from test_p5_envelope import crit


def _cfg():
    return copy.deepcopy(ALL_BLOCKS_CFG)


def test_capability_sheet_is_compact_and_has_hard_limits():
    sheet = capability_sheet()
    assert "CAPABILITY SHEET" in sheet
    assert "quota_vs_potential" in sheet
    assert "blocked path" in sheet.lower()
    assert len(sheet) < 4000          # must not recreate the 5.5k rulebook


def test_assess_flags_blocked_and_above_ceiling():
    doc = {"criteria": [
        crit("AC1", "quota_vs_potential", target_ratio_pct=120, band_pp=5),
        crit("AC2", "effective_capacity", target_pct=105, band_pp=3),
        crit("AC3", "revenue_vs_plan", segment="_all_", target_pct=95,
             band_pct=2),
    ]}
    by_id = {f["id"]: f for f in assess_criteria(doc)}
    assert by_id["AC1"]["reachable"] is False        # blocked path
    assert by_id["AC2"]["reachable"] is False        # > 100 ceiling
    assert by_id["AC2"]["nearest"] == 100.0
    assert by_id["AC3"]["reachable"] is True         # raking-exact


def test_assess_config_reports_the_gap_for_growth():
    doc = {"criteria": [crit("AC3", "core_vs_headline_growth",
                             min_headline_growth_pct=50,
                             max_core_growth_pct=-5)]}
    f = assess_config(_cfg(), doc)[0]
    assert f["reachable"] is False
    assert f["predicted"] is not None and f["predicted"] < 50
    assert f["nearest"] == f["predicted"]


def test_snap_criteria_clamps_and_records():
    doc = {"criteria": [crit("AC2", "effective_capacity", target_pct=105,
                             band_pp=3)]}
    nd, adj = snap_criteria(doc)
    assert nd["criteria"][0]["params"]["target_pct"] == 100.0
    assert adj and adj[0]["from"] == 105 and adj[0]["to"] == 100.0


def test_snap_criteria_noop_when_reachable():
    doc = {"criteria": [crit("AC2", "effective_capacity", target_pct=90,
                             band_pp=3)]}
    nd, adj = snap_criteria(doc)
    assert adj == []
    assert nd["criteria"][0]["params"]["target_pct"] == 90


def test_capability_workbench_is_bounded(tmp_path, monkeypatch):
    """Even a drafter that never fixes the target must terminate: at most
    `max_rounds` re-drafts, then one deterministic snap."""
    monkeypatch.chdir(tmp_path)
    from syngen import pipeline
    from syngen.session import Session

    calls = {"n": 0}

    def fake_redraft(*a, **k):
        calls["n"] += 1
        return a[2], True            # doc unchanged, claim-preserving

    monkeypatch.setattr(pipeline, "redraft_criteria", fake_redraft)
    session = Session.create(str(tmp_path / "sessions"), slug="cap")
    bad = {"criteria": [crit("AC2", "effective_capacity", target_pct=105,
                             band_pp=3)]}
    nd, adj = pipeline._capability_workbench(
        session, FakeLLM([]), "story", bad, {"claims": []}, "", _cfg(),
        lambda *a, **k: None, max_rounds=3)
    assert nd["criteria"][0]["params"]["target_pct"] == 100.0
    assert adj and adj[0]["to"] == 100.0
    assert calls["n"] == 3            # exactly the budget, then the snap
