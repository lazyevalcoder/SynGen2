"""P6 realizability wave - Part 1: the gate.

Regressions for the "criteria accepted that the generator cannot realize"
class (findings_v3.md batches 11-20):

- P1.1 unknown/hallucinated check names die at the consistency lint.
- P1.2 the engine tolerates configs that omit accounts.segments.
- P1.3 geometry findings get one bounded corrective re-draft before
  escalation (cohort pseudo-units from story nouns are re-expressible).
- P1.4 tier revenue-share targets that exceed the arithmetic ceiling are
  flagged as infeasible at the cross-lint.
"""
import json

from syngen.generator.engine import generate_to_workbook
from syngen.phases.criteria_lint import (cross_lint, lint_criteria_internal)

from test_p5_envelope import base_cfg, crit


def llm_json(obj):
    from syngen.llm.client import LLMResponse
    return LLMResponse(content=json.dumps(obj))


# --- P1.1: unknown check names -------------------------------------------


def test_unknown_check_is_a_hard_finding():
    doc = {"criteria": [
        crit("AC1", "revenue_vs_plan", segment="_all_", dimension="segment",
             target_pct=95, band_pct=2),
        crit("AC2", "post_change_bookings_decline", min_gap_pp=5),
    ]}
    hard, _ = lint_criteria_internal(doc)
    assert any("not in the pack's check registry" in h for h in hard)


def test_unknown_check_escalates_in_pipeline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from syngen.llm.client import FakeLLM
    from syngen.pipeline import run_new_story
    from test_pipeline import AUDIT_COVERED, PRECHECK, SilentIO

    bad = {"definitions": {}, "criteria": [
        crit("AC1", "revenue_vs_plan", segment="_all_", dimension="segment",
             target_pct=95, band_pct=2),
        crit("AC2", "post_change_bookings_decline", min_gap_pp=5),
    ]}
    client = FakeLLM([
        llm_json(PRECHECK),
        llm_json(bad),        # draft 1 -> lint hard (unknown check)
        llm_json(AUDIT_COVERED),
        llm_json(bad),        # corrective re-draft: still hallucinated
        llm_json(AUDIT_COVERED),
    ])
    result = run_new_story(client, "Post-change bookings declined.",
                           SilentIO(), sessions_dir="sessions",
                           slug="unknowncheck", use_critic=False)
    assert result["status"] == "escalated"
    assert result["reason"] == "criteria_consistency"
    sdir = next((tmp_path / "sessions").iterdir())
    log_text = (sdir / "session_log.md").read_text(encoding="utf-8")
    assert "not in the pack's check registry" in log_text


# --- P1.2: segments default -----------------------------------------------


def test_engine_defaults_segments_when_absent(tmp_path):
    cfg = base_cfg()
    del cfg["accounts"]["segments"]
    cfg["output"] = {"workbook": str(tmp_path / "out.xlsx")}
    frames, _ = generate_to_workbook(cfg)
    acc = frames["accounts"]
    assert "segment" in acc.columns
    assert set(acc["segment"].unique()) == {"All"}


# --- P1.3: geometry lint corrective re-draft -------------------------------


def _cfg_with_quota():
    cfg = base_cfg()
    cfg["quota"] = {
        "by_segment": {
            "Enterprise": [100000.0] * 4,
            "SMB": [40000.0] * 4,
        },
        "attainment_by_segment": {"Enterprise": 1.0, "SMB": 1.0},
    }
    return cfg


def test_geometry_redraft_escalates_if_still_bad(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from syngen.llm.client import FakeLLM
    from syngen.pipeline import run_new_story
    from test_pipeline import AUDIT_COVERED, PRECHECK, SilentIO

    sim = _cfg_with_quota()
    bad = {"definitions": {}, "criteria": [
        crit("AC3", "quota_vs_potential", dimension="territory",
             unit="small_territories", target_ratio_pct=70, band_pp=10),
        crit("AC4", "data_sanity", max_discount_pct=40),
    ]}
    client = FakeLLM([
        llm_json(PRECHECK),
        llm_json(bad),          # draft 1 -> cross-lint fires
        llm_json(AUDIT_COVERED),
        llm_json(sim),          # simulator draft (quota block present)
        llm_json(bad),          # corrective criteria re-draft: still bad
        llm_json(AUDIT_COVERED),
    ])
    result = run_new_story(client, "Quotas mismatch potential.",
                           SilentIO(), sessions_dir="sessions",
                           slug="geobad", use_critic=False)
    assert result["status"] == "escalated"
    assert result["reason"] == "criteria_geometry"
    sdir = next((tmp_path / "sessions").iterdir())
    log_text = (sdir / "session_log.md").read_text(encoding="utf-8")
    assert "corrective re-draft" in log_text
    assert "outside the data model" in log_text


def test_cross_lint_flags_pseudo_cohort_unit():
    findings = cross_lint(_cfg_with_quota(), {"criteria": [
        crit("AC3", "quota_vs_potential", dimension="territory",
             unit="small_territories", target_ratio_pct=70, band_pp=10)]})
    assert any("'small_territories'" in f and "outside the data model" in f
               for f in findings)


# --- P1.4: tier-share reachability -----------------------------------------


def test_tier_share_target_above_ceiling_is_flagged():
    cfg = base_cfg()
    # entry at 0.45x can never carry 80% of revenue while other tiers exist.
    findings = cross_lint(cfg, {"criteria": [
        crit("AC3", "tier_share_shift", tier="entry",
             from_share_pct=20, to_share_pct=80, tolerance_pp=5)]})
    assert any("arithmetically unreachable" in f for f in findings)


def test_tier_share_reasonable_target_is_not_flagged():
    cfg = base_cfg()
    findings = cross_lint(cfg, {"criteria": [
        crit("AC3", "tier_share_shift", tier="core",
             from_share_pct=20, to_share_pct=45, tolerance_pp=5)]})
    assert not any("arithmetically unreachable" in f for f in findings)
