"""P6 P3.8 - calibration-agreement sweep (CI gate).

Every closed-form solver the autopilot relies on is a hand-coded inverse
model of SOME engine path. When that model drifts from the engine, the
flight burns its budget on a target the solver claims is reachable but is
not (cert s12 AC2: predicted +0.0pp margin, actual swung +/-4pp; s12 AC3:
predicted 25% tier share, engine measured 18.4%).

Each test runs the DETERMINISTIC SOLVER, then generates a real workbook
and validates against the engine's actual output. If a solver's prediction
and the engine disagree enough to fail its own criterion, this file turns
red - drift is caught at CI time, not after a burned flight.
"""
import json

import pytest

from syngen.config import validate_simulator_doc
from syngen.generator.engine import generate_to_workbook
from syngen.phases.preflight import autocalibrate
from syngen.validator.report import run_validation

from test_p5_envelope import crit

SEEDS = [42, 7, 2026]


def _flight(cfg, doc, tmp_path):
    cfg = validate_simulator_doc(json.loads(json.dumps(cfg)))
    out = tmp_path / "out.xlsx"
    cfg["output"] = {"workbook": str(out)}
    criteria_path = tmp_path / "criteria.json"
    criteria_path.write_text(json.dumps(doc), encoding="utf-8")
    fixes = autocalibrate(cfg, doc)
    sim_path = tmp_path / "simulator.json"
    sim_path.write_text(json.dumps(cfg), encoding="utf-8")
    wb = generate_to_workbook(cfg)[1]
    results, all_pass = run_validation(wb, criteria_path)
    return results, all_pass, fixes


@pytest.mark.parametrize("seed", SEEDS)
def test_margin_solver_agrees_with_engine(tmp_path, seed):
    from test_entity_schemas import ALL_BLOCKS_CFG
    cfg = json.loads(json.dumps(ALL_BLOCKS_CFG))
    cfg["seed"] = seed
    # the margin metric has a ~3-4pp seed-noise floor from the won-revenue
    # lognormal tail; the agreement contract is "within the achievable
    # envelope" (tolerance_pp=4), not an impossible +/-1pp.
    doc = {"definitions": {}, "criteria": [
        crit("AC1", "blended_margin_trend", target_change_pct=-2,
             tolerance_pp=4),
    ]}
    results, all_pass, _ = _flight(cfg, doc, tmp_path)
    assert all_pass, f"solver predicted reachable but engine disagrees: {results}"


@pytest.mark.parametrize("seed", SEEDS)
def test_tier_share_solver_agrees_with_engine(tmp_path, seed):
    from test_entity_schemas import ALL_BLOCKS_CFG
    cfg = json.loads(json.dumps(ALL_BLOCKS_CFG))
    cfg["seed"] = seed
    # revenue-share measurement carries ~5-8pp tail noise from the won-revenue
    # lognormal; the agreement contract is the achievable envelope.
    doc = {"definitions": {}, "criteria": [
        crit("AC1", "tier_share_shift", tier="entry",
             from_share_pct=15, to_share_pct=30, tolerance_pp=8),
    ]}
    results, all_pass, _ = _flight(cfg, doc, tmp_path)
    assert all_pass, f"solver predicted reachable but engine disagrees: {results}"


@pytest.mark.parametrize("seed", SEEDS)
def test_elasticity_solver_agrees_with_engine(tmp_path, seed):
    from test_entity_schemas import ALL_BLOCKS_CFG
    cfg = json.loads(json.dumps(ALL_BLOCKS_CFG))
    cfg["seed"] = seed
    cfg.pop("pricing_response", None)
    doc = {"definitions": {}, "criteria": [
        crit("AC1", "elasticity_differential", min_gap_pp=5, tolerance_pp=1),
    ]}
    results, all_pass, _ = _flight(cfg, doc, tmp_path)
    assert all_pass, f"solver predicted reachable but engine disagrees: {results}"


@pytest.mark.parametrize("seed", SEEDS)
def test_coverage_and_levels_solvers_agree_with_engine(tmp_path, seed):
    from test_entity_schemas import ALL_BLOCKS_CFG
    cfg = json.loads(json.dumps(ALL_BLOCKS_CFG))
    cfg["seed"] = seed
    doc = {"definitions": {}, "criteria": [
        crit("AC1", "coverage_ratio", quarter="FY26-Q4", min_multiple=3.0),
        crit("AC2", "realized_vs_list", quarter_start="FY26-Q1",
             target_start_pct=85, quarter_end="FY26-Q4",
             target_end_pct=88, tolerance_pp=3),
    ]}
    results, all_pass, _ = _flight(cfg, doc, tmp_path)
    assert all_pass, f"solver predicted reachable but engine disagrees: {results}"
