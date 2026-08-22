"""M3: schema linter (FR4) - E's trap stories adapted to simulator.json shape."""
import copy

import pytest

from syngen.generator.engine import generate_to_workbook
from syngen.linter import has_blocking, lint, structure_findings


@pytest.fixture
def clean_cfg():
    return {
        "seed": 42,
        "time_model": {
            "fiscal_year": "FY26",
            "quarter_labels": ["FY26-Q1", "FY26-Q2"],
            "quarter_end_dates": ["2026-03-31", "2026-06-30"],
        },
        "output": {"workbook": "output/dataset.xlsx"},
        "accounts": {
            "count": 40,
            "regions": {"AMER": 0.45, "EMEA": 0.30, "APAC": 0.25},
            "segments": {"Enterprise": 0.3, "Mid-Market": 0.4,
                         "SMB": 0.2, "CSB": 0.1},
            "industries": ["Software", "Retail"],
        },
        "opportunities": {"per_quarter": 120},
    }


def by_rule(findings, rule):
    return [f for f in findings if f[0] == rule]


def test_clean_config_lints_clean(clean_cfg):
    assert lint(clean_cfg) == []
    assert not has_blocking(lint(clean_cfg))


def test_r1_synonym_fact_table_blocked(clean_cfg):
    cfg = copy.deepcopy(clean_cfg)
    cfg["deals"] = {"per_quarter": 100}
    findings = lint(cfg)
    r1 = by_rule(findings, "R1")
    assert any(sev == "FAIL" for _, sev, _ in r1)


def test_r1_unknown_block_warns_not_blocks(clean_cfg):
    cfg = copy.deepcopy(clean_cfg)
    cfg["widgets"] = {"count": 5}
    findings = lint(cfg)
    r1 = by_rule(findings, "R1")
    assert r1 and all(sev == "WARN" for _, sev, _ in r1)
    assert has_blocking(findings) is False


def test_r2_stored_aggregate_blocked(clean_cfg):
    cfg = copy.deepcopy(clean_cfg)
    cfg["metrics_rollup"] = {"rows": 4}
    assert has_blocking(by_rule(lint(cfg), "R2"))


def test_r4_taxonomy_subset_is_advisory_only(clean_cfg):
    """F8: story names Enterprise/MM/SMB, world silently loses CSB."""
    cfg = copy.deepcopy(clean_cfg)
    cfg["accounts"]["segments"] = {"Enterprise": 0.4, "Mid-Market": 0.35,
                                   "SMB": 0.25}
    findings = lint(cfg)
    r4 = by_rule(findings, "R4")
    assert len(r4) == 1
    rule, sev, msg = r4[0]
    assert sev == "ADVISE"
    assert "CSB" in msg
    assert not has_blocking(findings)


def test_r3_dangling_reference_warns(clean_cfg):
    cfg = copy.deepcopy(clean_cfg)
    cfg["widgets"] = {"fields": {"contact_id": {"type": "categorical"}}}
    findings = lint(cfg)
    r3 = by_rule(findings, "R3")
    assert r3 and "contact_id" in r3[0][2]


def test_r3_declared_reference_passes(clean_cfg):
    cfg = copy.deepcopy(clean_cfg)
    cfg["contacts"] = {
        "references": ["accounts"],
        "fields": {"account_id": {"type": "categorical"}},
    }
    # 'contacts' itself triggers R1 WARN; the point is no R3 finding
    assert by_rule(lint(cfg), "R3") == []


def test_r5_overlapping_status_fields_blocked(clean_cfg):
    cfg = copy.deepcopy(clean_cfg)
    cfg["opps_ext"] = {
        "fields": {
            "stage": {"values": ["Open", "Closed Won", "Closed Lost"]},
            "win_status": {"values": ["Won", "Lost", "Closed Won"]},
        }
    }
    findings = lint(cfg)
    r5 = [f for f in by_rule(findings, "R5") if f[1] == "FAIL"]
    assert len(r5) == 1
    assert "overlapping status" in r5[0][2]


# --- post-generation structural check ---------------------------------------

def _gen_workbook(tmp_path):
    from syngen.config import validate_simulator_doc
    cfg = validate_simulator_doc({
        "seed": 42,
        "time_model": {
            "fiscal_year": "FY26",
            "quarter_labels": ["FY26-Q1"],
            "quarter_end_dates": ["2026-03-31"],
        },
        "output": {"workbook": str(tmp_path / "ds.xlsx")},
        "accounts": {
            "count": 20,
            "regions": {"AMER": 0.5, "EMEA": 0.5},
            "segments": {"Enterprise": 0.5, "SMB": 0.5},
            "industries": ["Software"],
        },
        "opportunities": {
            "per_quarter": 50,
            "win_rate": 0.3,
            "win_rate_jitter": 0.01,
            "owners": ["A Rep"],
            "deal_duration_days": [10, 40],
            "close_clustering": {"share_in_end_of_quarter_window": 0.25},
            "deal_size_lognormal": {"median_usd": 40000, "sigma": 0.7},
            "discount": {
                "base_by_quarter": {"AMER": [12], "EMEA": [13]},
                "noise_sd_pp": 2,
                "end_of_quarter_boost_pp": 5,
                "end_of_quarter_window_days": 10,
                "min_pct": 0,
                "max_pct": 40,
            },
        },
    })
    _, path = generate_to_workbook(cfg)
    return path


def test_structure_gate_passes_on_engine_output(tmp_path):
    path = _gen_workbook(tmp_path)
    assert structure_findings(path) == []


def test_structure_gate_catches_extra_sheet(tmp_path):
    import pandas as pd
    path = _gen_workbook(tmp_path)
    with pd.ExcelWriter(path, engine="openpyxl", mode="a",
                        if_sheet_exists="replace") as writer:
        pd.DataFrame({"x": [1]}).to_excel(writer, sheet_name="deals",
                                          index=False)
    findings = structure_findings(path)
    assert any("unexpected sheet 'deals'" in m for _, _, m in findings)


def test_structure_gate_catches_missing_sheet(tmp_path):
    import openpyxl
    path = _gen_workbook(tmp_path)
    wb = openpyxl.load_workbook(path)
    del wb["quarterly_summary"]
    wb.save(path)
    findings = structure_findings(path)
    assert any("missing required sheet 'quarterly_summary'" in m
               for _, _, m in findings)


def test_structure_gate_catches_column_drift(tmp_path):
    import pandas as pd
    path = _gen_workbook(tmp_path)
    frames = {}
    for sheet in ("accounts", "opportunities", "quarterly_summary"):
        frames[sheet] = pd.read_excel(path, sheet_name=sheet)
    meta = pd.read_excel(path, sheet_name="_synngen_meta")
    frames["accounts"].drop(columns=["industry"]).to_excel(
        pd.ExcelWriter(path, engine="openpyxl"), sheet_name="accounts",
        index=False)
    # rewrite remaining sheets so only the column drift differs
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        frames["accounts"].drop(columns=["industry"]).to_excel(
            writer, sheet_name="accounts", index=False)
        frames["opportunities"].to_excel(writer, sheet_name="opportunities",
                                         index=False)
        frames["quarterly_summary"].to_excel(
            writer, sheet_name="quarterly_summary", index=False)
        meta.to_excel(writer, sheet_name="_synngen_meta", index=False)
    findings = structure_findings(path)
    assert any("'accounts'" in m and "column mismatch" in m
               for _, _, m in findings)
