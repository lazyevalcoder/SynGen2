"""Entity-schema tripwires (M6 P3.5).

The packs/revops/entities/*.json files are the machine-readable mirror of
docs/ENTITY_SCHEMA.md. Three guarantees:

1. the repo pack loads with structurally valid schemas;
2. every claim-matrix cell resolves to an entity a schema materializes;
3. generated workbook headers EQUAL the schema contract - engine drift
   from the documented data model becomes a CI failure, not folklore.

Plus a UAT coverage check: every config block the 25 certification
scenarios use must be expressible through the schemas' presence/when refs.
"""
import json
from pathlib import Path

import pandas as pd
import pytest

from syngen.config import validate_simulator_doc
from syngen.generator.engine import generate_to_workbook
from syngen.packs.loader import ensure_valid

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pack():
    p, warnings = ensure_valid()
    return p


# --- 1. structural validity ----------------------------------------------------


def test_repo_pack_carries_all_ten_artifact_schemas(pack):
    assert sorted(pack.entity_schemas) == [
        "account_activity", "account_ownership", "accounts",
        "capacity_plan", "forecast_snapshot", "opportunities",
        "opportunity_stage_history", "quarterly_summary", "quota_plan",
        "reps"]


def test_every_matrix_cell_entity_is_materialized_by_a_schema(pack):
    matrix_entities = {cell["entity"] for cell in
                       pack.claims_matrix["cells"]}
    materialized = set()
    for doc in pack.entity_schemas.values():
        materialized.update(doc.get("entities", []))
    uncovered = sorted(matrix_entities - materialized)
    assert not uncovered, f"cells reference unmaterialized entities: {uncovered}"


# --- 2. header drift tripwire ---------------------------------------------------

ALL_BLOCKS_CFG = {
    "seed": 42,
    "time_model": {
        "fiscal_year": "FY26",
        "quarter_labels": ["FY26-Q1", "FY26-Q2", "FY26-Q3", "FY26-Q4"],
        "quarter_end_dates": ["2026-03-31", "2026-06-30",
                              "2026-09-30", "2026-12-31"],
    },
    "output": {"workbook": "out.xlsx"},
    "accounts": {
        "count": 40,
        "regions": {"AMER": 0.6, "EMEA": 0.4},
        "segments": {"Enterprise": 0.5, "SMB": 0.5},
        "industries": ["Software"],
        "territories": {
            "AMER-East": ["AMER"], "AMER-West": ["AMER"],
            "EMEA": ["EMEA"],
        },
    },
    "products": {
        "catalog": [
            {"id": "ENTRY-001", "tier": "entry", "share": 0.4},
            {"id": "CORE-001", "tier": "core", "share": 0.4},
            {"id": "PREM-001", "tier": "premium", "share": 0.2},
        ],
        "margin_by_tier": {"entry": 0.55, "core": 0.7, "premium": 0.8},
        "price_multiplier_by_tier": {"entry": 0.45, "core": 1.0,
                                     "premium": 2.4},
        "discount_delta_pp_by_tier": {"entry": 0, "core": 0, "premium": 0},
        "cogs_inflation_by_quarter": [1.0, 1.0, 1.0, 1.0],
    },
    "opportunities": {
        "per_quarter": 60,
        "win_rate": 0.3,
        "win_rate_jitter": 0.005,
        "owners": ["A Rep", "B Rep"],
        "deal_duration_days": {"means": [40, 40, 40, 40]},
        "close_clustering": {"share_in_end_of_quarter_window": 0.25},
        "deal_size_lognormal": {"median_usd": 40000, "sigma": 0.6},
        "outlier_deals": {
            "share_by_quarter": [0.01, 0.01, 0.01, 0.01],
            "multiplier": 20,
        },
        "discount": {
            "base_by_quarter": {"AMER": [10, 10, 10, 10],
                                "EMEA": [10, 10, 10, 10]},
            "noise_sd_pp": 2,
            "end_of_quarter_boost_pp": 4,
            "end_of_quarter_window_days": 10,
            "min_pct": 0, "max_pct": 40,
        },
    },
    "pipeline": {
        "stage_names": ["Discovery", "Proposal"],
        "share_open_by_quarter": [0.02, 0.04, 0.06, 0.40],
        "slippage_rate_by_quarter": [0.05, 0.15, 0.25, 0.35],
    },
    "quota": {
        "by_motion": {
            "New Logo": [50000.0] * 4,
            "Expansion": [60000.0] * 4,
        },
        "attainment_by_motion": {"New Logo": 1.0, "Expansion": 1.0},
    },
    "capacity": {
        "by_territory": {
            unit: {"headcount_plan": [10] * 4, "headcount_actual": [9] * 4,
                   "ramping_reps_by_quarter": [2] * 4,
                   "ramp_productivity_pct": 45}
            for unit in ["AMER-East", "AMER-West", "EMEA"]
        },
    },
    "ownership": {
        "churn_share_by_quarter": [0.0, 0.0, 0.0, 0.3],
        "unowned_share_by_quarter": [0.0, 0.0, 0.0, 0.0],
        "owner_pool": ["A Rep", "B Rep", "C Rep"],
        "win_rate_multiplier_after_change": 0.45,
    },
    "activity": {
        "mean_touches_per_account_by_quarter": [1.2] * 4,
        "potential_tilt": -0.3,
    },
    "forecast": {
        "commit_ratio_by_quarter": [1.0] * 4,
        "commit_share_of_won_by_quarter": [0.5] * 4,
        "low_activity_bias": 3.0,
    },
    "pricing_response": {
        "price_change_pct_by_quarter": [0.0, 0.0, 10.0, 10.0],
        "elasticity": -6.0,
        "potential_mitigation": 1.0,
    },
}


def _schema_expected_headers(cfg):
    """Derive {sheet: [columns]} purely from the pack schemas."""
    pack, _ = ensure_valid()
    sheets = {}
    for sname, doc in sorted(pack.entity_schemas.items()):
        presence = doc["presence"]
        if presence != "always" and not cfg.get(presence.split(".")[0]):
            continue
        cols = []
        for col in doc["columns"]:
            when = col.get("when")
            if when:
                head, _, sub = when.partition(".")
                block = cfg.get(head)
                if not block or (sub and not block.get(sub)):
                    continue
            if col.get("alternatives"):
                # plan-dimension alternates: territory when capacity is
                # territorial, else region
                chosen = "territory" if \
                    (cfg.get("capacity") or {}).get("by_territory") \
                    else "region"
                cols.append({**col, "name": chosen})
            else:
                cols.append(col)
        sheets[doc["sheet"]] = [c["name"] for c in cols]
    return sheets


def test_generated_headers_equal_schema_contract(tmp_path):
    cfg = validate_simulator_doc(json.loads(json.dumps(ALL_BLOCKS_CFG)))
    cfg["output"]["workbook"] = str(tmp_path / "ds.xlsx")
    _, wb = generate_to_workbook(cfg)

    xl = pd.ExcelFile(wb)
    actual = {s: list(pd.read_excel(wb, sheet_name=s).columns)
              for s in xl.sheet_names}
    expected = _schema_expected_headers(cfg)
    for sheet, exp_cols in expected.items():
        assert sheet in actual, f"schema sheet '{sheet}' missing in workbook"
        assert actual[sheet] == exp_cols, (
            f"sheet '{sheet}' drifted from entity schema:\n"
            f"  schema:   {exp_cols}\n  workbook: {actual[sheet]}")
    extra = set(actual) - set(expected) - {"_synngen_meta"}
    assert not extra, f"workbook sheets no schema documents: {extra}"


def test_baseline_config_hides_conditional_columns(tmp_path):
    bare_opp = {k: v for k, v in ALL_BLOCKS_CFG["opportunities"].items()
                if k != "outlier_deals"}
    bare_acc = {k: v for k, v in ALL_BLOCKS_CFG["accounts"].items()
                if k != "territories"}
    cfg = validate_simulator_doc(json.loads(json.dumps({
        "seed": ALL_BLOCKS_CFG["seed"],
        "time_model": ALL_BLOCKS_CFG["time_model"],
        "output": ALL_BLOCKS_CFG["output"],
        "accounts": bare_acc,
        "opportunities": bare_opp,
    })))
    cfg["output"]["workbook"] = str(tmp_path / "ds.xlsx")
    _, wb = generate_to_workbook(cfg)
    opp_cols = list(pd.read_excel(wb, sheet_name="opportunities").columns)
    expected = _schema_expected_headers(cfg)["opportunities"]
    assert opp_cols == expected == [
        "opportunity_id", "account_id", "owner", "region", "segment", "icp",
        "fiscal_quarter", "created_date", "close_date", "stage",
        "list_price", "discount_pct", "realized_price"]
    assert set(pd.ExcelFile(wb).sheet_names) >= \
        {"accounts", "opportunities", "quarterly_summary", "_synngen_meta"}
    assert "quota_plan" not in pd.ExcelFile(wb).sheet_names


# --- 3. UAT block coverage ------------------------------------------------------

BASE_BLOCKS = {"seed", "time_model", "output"}


def _schema_block_refs(pack):
    refs = set()
    for doc in pack.entity_schemas.values():
        if doc["presence"] != "always":
            refs.add(doc["presence"])
        for col in doc["columns"]:
            if col.get("when"):
                refs.add(col["when"])
        refs.update(doc.get("blocks_used", []))
    return refs


STRUCTURAL_SUBKEYS = {
    "accounts": "territories",
    "quota": "by_motion",
    "opportunities": "outlier_deals",
    "capacity": "by_territory",
}


@pytest.mark.skipif(
    not (REPO_ROOT / "uat").is_dir(), reason="uat scenarios not present")
def test_uat_scenario_blocks_are_expressible_in_schemas(pack):
    refs = _schema_block_refs(pack)
    uat_root = REPO_ROOT / "uat"
    problems = []
    n_scenarios = 0
    for sim in sorted(uat_root.glob("scenario_*/simulator.json")):
        n_scenarios += 1
        cfg = json.loads(sim.read_text(encoding="utf-8"))
        for block, spec in cfg.items():
            if block.startswith("_"):
                continue
            if block in BASE_BLOCKS:
                continue
            if block.split(".")[0] not in {r.split(".")[0] for r in refs}:
                problems.append(f"{sim.name}: block '{block}' unknown")
            sub = STRUCTURAL_SUBKEYS.get(block)
            if sub and isinstance(spec, dict) and spec.get(sub) and \
                    f"{block}.{sub}" not in refs:
                problems.append(f"{sim.name}: '{block}.{sub}' not in schemas")
    assert n_scenarios == 25, f"expected 25 UAT scenarios, saw {n_scenarios}"
    assert not problems, "UAT configs use refs the schemas cannot express:" \
                         f"\n" + "\n".join(problems)


@pytest.mark.skipif(
    not (REPO_ROOT / "uat").is_dir(), reason="uat scenarios not present")
def test_uat_criteria_checks_are_pack_declared(pack):
    uat_root = REPO_ROOT / "uat"
    undeclared = []
    for crit_file in sorted(uat_root.glob("scenario_*/criteria.json")):
        doc = json.loads(crit_file.read_text(encoding="utf-8"))
        for c in doc.get("criteria", []):
            if c.get("check") and c["check"] not in pack.checks:
                undeclared.append(f"{crit_file.parent.name}: {c['check']}")
    assert not undeclared, \
        "UAT criteria use checks outside the pack:\n" + "\n".join(undeclared)
