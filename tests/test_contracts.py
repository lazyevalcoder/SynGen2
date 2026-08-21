"""Contract enforcement tests: BOM rejection, schema validation, duplicate IDs."""
import json
from pathlib import Path

import pytest

from syngen.config import ConfigError, load_criteria, load_simulator


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_bytes(text.encode("utf-8"))
    return p


MINIMAL_SIM = {
    "seed": 1,
    "time_model": {
        "fiscal_year": "FY26",
        "quarter_labels": ["FY26-Q1"],
        "quarter_end_dates": ["2026-03-31"],
    },
    "output": {"workbook": "out.xlsx"},
    "accounts": {
        "count": 5,
        "regions": {"AMER": 1.0},
        "segments": {"SMB": 1.0},
        "industries": ["Software"],
    },
    "opportunities": {
        "per_quarter": 10,
        "win_rate": 0.3,
        "win_rate_jitter": 0.0,
        "owners": ["Rep"],
        "deal_duration_days": [20, 30],
        "close_clustering": {"share_in_end_of_quarter_window": 0.3},
        "deal_size_lognormal": {"median_usd": 45000, "sigma": 0.8},
        "discount": {
            "base_by_quarter": {"AMER": [12]},
            "noise_sd_pp": 3,
            "end_of_quarter_boost_pp": 6.5,
            "end_of_quarter_window_days": 14,
            "min_pct": 0,
            "max_pct": 40,
        },
    },
}

MINIMAL_CRITERIA = {
    "definitions": {},
    "criteria": [
        {"id": "AC1", "name": "x", "check": "win_rate_flat", "params": {}},
    ],
}


def test_valid_configs_load(tmp_path):
    sim = write(tmp_path, "sim.json", json.dumps(MINIMAL_SIM))
    crit = write(tmp_path, "crit.json", json.dumps(MINIMAL_CRITERIA))
    assert load_simulator(sim)["seed"] == 1
    assert len(load_criteria(crit)["criteria"]) == 1


def test_bom_rejected(tmp_path):
    p = tmp_path / "bom.json"
    p.write_bytes(b"\xef\xbb\xbf" + json.dumps(MINIMAL_SIM).encode("utf-8"))
    with pytest.raises(ConfigError, match="BOM"):
        load_simulator(p)


def test_missing_key_rejected(tmp_path):
    bad = dict(MINIMAL_SIM)
    del bad["seed"]
    p = write(tmp_path, "bad.json", json.dumps(bad))
    with pytest.raises(ConfigError, match="missing keys"):
        load_simulator(p)


def test_curve_length_mismatch_rejected(tmp_path):
    bad = json.loads(json.dumps(MINIMAL_SIM))
    bad["time_model"]["quarter_labels"] = ["FY26-Q1", "FY26-Q2"]
    p = write(tmp_path, "bad.json", json.dumps(bad))
    with pytest.raises(ConfigError, match="one value per quarter|length mismatch|length"):
        load_simulator(p)


def test_duplicate_criterion_id_rejected(tmp_path):
    bad = json.loads(json.dumps(MINIMAL_CRITERIA))
    bad["criteria"].append(dict(bad["criteria"][0]))
    p = write(tmp_path, "bad.json", json.dumps(bad))
    with pytest.raises(ConfigError, match="duplicate criterion id"):
        load_criteria(p)


def test_unknown_check_name_is_not_a_config_error():
    """Unknown checks are a validation-time ERROR row, not a config crash (report handles)."""
    from syngen.validator.report import CHECKS
    assert "win_rate_flat" in CHECKS
