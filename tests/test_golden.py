"""Golden session test: the converged Experiment D config must reproduce its
8/8 PASS verdict through the package. This is the regression anchor for M1."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from syngen.generator.engine import generate, write_workbook
from syngen.validator.report import run_validation

GOLDEN_DIR = Path(__file__).parent / "golden"
GOLDEN_SIM = GOLDEN_DIR / "golden_simulator.json"
GOLDEN_CRITERIA = GOLDEN_DIR / "golden_criteria.json"

EXPECTED_SUMMARY = {
    # quarter: (win_rate_pct, avg_discount_won_pct) from the converged D run
    "FY26-Q1": (27.00, 13.05),
    "FY26-Q2": (28.75, 15.69),
    "FY26-Q3": (28.25, 18.89),
    "FY26-Q4": (25.50, 19.16),
}


@pytest.fixture(scope="module")
def golden_workbook(tmp_path_factory):
    frames = generate(GOLDEN_SIM)
    path = tmp_path_factory.mktemp("golden") / "golden.xlsx"
    write_workbook(frames, path)
    return frames, path


def test_golden_summary_matches_converged_run(golden_workbook):
    """Same seed + same config must reproduce the exact numbers D landed on."""
    frames, _ = golden_workbook
    s = frames["quarterly_summary"].set_index("fiscal_quarter")
    for label, (win_rate, avg_disc) in EXPECTED_SUMMARY.items():
        assert s.loc[label, "win_rate_pct"] == win_rate, f"{label} win rate drifted"
        assert s.loc[label, "avg_discount_won_pct"] == avg_disc, f"{label} discount drifted"


def test_golden_session_validates_8_of_8(golden_workbook):
    _, path = golden_workbook
    results, all_pass = run_validation(path, GOLDEN_CRITERIA)
    assert len(results) == 8
    failed = [r["id"] for r in results if r["verdict"] != "PASS"]
    assert all_pass, f"golden session must land the story; failing: {failed}"


def test_golden_passing_margins_are_positive(golden_workbook):
    _, path = golden_workbook
    results, _ = run_validation(path, GOLDEN_CRITERIA)
    thin = [r["id"] for r in results if r["margin"] <= 0]
    assert not thin, f"passing criteria must carry positive margins: {thin}"
