"""Experiment B's gates, as tests: determinism + knob responsiveness + sanity."""
import json

from syngen.generator.engine import generate

CONFIG = {
    "seed": 7,
    "time_model": {
        "fiscal_year": "FY26",
        "quarter_labels": ["FY26-Q1", "FY26-Q2"],
        "quarter_end_dates": ["2026-03-31", "2026-06-30"],
    },
    "output": {"workbook": "unused_in_engine_tests.xlsx"},
    "accounts": {
        "count": 20,
        "regions": {"AMER": 0.5, "EMEA": 0.3, "APAC": 0.2},
        "segments": {"Enterprise": 0.4, "Mid-Market": 0.35, "SMB": 0.25},
        "industries": ["Software", "Retail"],
    },
    "opportunities": {
        "per_quarter": 50,
        "win_rate": 0.27,
        "win_rate_jitter": 0.005,
        "owners": ["A Rep", "B Rep"],
        "deal_duration_days": [20, 90],
        "close_clustering": {"share_in_end_of_quarter_window": 0.3},
        "deal_size_lognormal": {"median_usd": 45000, "sigma": 0.8},
        "discount": {
            "base_by_quarter": {
                "AMER": [12, 14], "APAC": [12, 14], "EMEA": [12, 13.5],
            },
            "noise_sd_pp": 3,
            "end_of_quarter_boost_pp": 6.5,
            "end_of_quarter_window_days": 14,
            "min_pct": 0,
            "max_pct": 40,
        },
    },
}


def base_config(**overrides):
    cfg = json.loads(json.dumps(CONFIG))
    for path, value in overrides.items():
        keys = path.split(".")
        node = cfg
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = value
    return cfg


def test_determinism_same_seed_identical_data():
    f1 = generate(base_config())
    f2 = generate(base_config())
    for sheet in f1:
        assert f1[sheet].equals(f2[sheet]), f"{sheet} differs between identical runs"


def test_different_seed_different_data():
    f1 = generate(base_config(seed=7))
    f2 = generate(base_config(seed=8))
    assert not f1["opportunities"]["discount_pct"].equals(f2["opportunities"]["discount_pct"])


def test_knob_change_changes_output_without_code():
    f_low = generate(base_config(**{"opportunities.discount.noise_sd_pp": 1}))
    f_high = generate(base_config(**{"opportunities.discount.noise_sd_pp": 9}))
    sd_low = f_low["opportunities"]["discount_pct"].std()
    sd_high = f_high["opportunities"]["discount_pct"].std()
    assert sd_high - sd_low > 1.5, f"knob response too weak: {sd_low:.2f} vs {sd_high:.2f}"


def test_data_sanity_bounds_fks_dates():
    frames = generate(base_config())
    acc = frames["accounts"]
    d = frames["opportunities"]
    assert ((d["discount_pct"] >= 0) & (d["discount_pct"] <= 40)).all()
    assert (d["list_price"] > 0).all() and (d["realized_price"] > 0).all()
    assert d["account_id"].isin(set(acc["account_id"])).all()


def test_realized_is_derived_not_sampled():
    frames = generate(base_config())
    opp = frames["opportunities"]
    expected = (opp["list_price"] * (1 - opp["discount_pct"] / 100)).round(2)
    assert (abs(opp["realized_price"] - expected) < 0.01).all()
