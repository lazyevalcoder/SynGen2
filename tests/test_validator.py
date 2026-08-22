"""Experiment C's two-direction gate, as tests: broken data fails, margins behave."""
import numpy as np
import pandas as pd
import pytest

from syngen.validator.checks import CHECKS

CRITERIA_PARAMS = {
    "win_rate_flat": {"band_pp": 3.0},
    "avg_discount_quarter": {"quarter": "FY26-Q4", "target_pct": 18.0, "tolerance_pp": 2.0},
    "discount_trend_monotonic": {"max_dip_pp": 1.0},
    "region_discount_premium": {
        "region": "EMEA", "vs": ["AMER", "APAC"],
        "min_premium_pp": 5.0, "quarters": ["FY26-Q3", "FY26-Q4"],
    },
    "end_of_quarter_effect": {"window_days": 14, "min_gap_pp": 5.0},
    "realized_vs_list": {
        "quarter_start": "FY26-Q1", "target_start_pct": 88.0,
        "quarter_end": "FY26-Q4", "target_end_pct": 82.0, "tolerance_pp": 2.0,
    },
    "data_sanity": {"max_discount_pct": 40.0},
    # plan targets injected at runtime from the data itself (see run_check)
    "revenue_vs_plan": {"segment": "Enterprise", "band_pct": 2.0},
    # fixture uses near-flat durations/counts, so zero-growth bands pass
    "cycle_length_trend": {"min_increase_pct": 0.0},
    "creation_volume_trend": {"target_decline_pct": 0.0, "tolerance_pp": 1.0},
    # M5 iter 1 checks (fixture has ~80 won deals/quarter at sigma=0.8 ->
    # quarterly size averages wobble several %; bands must be honest)
    "deal_size_trend": {"target_change_pct": 0.0, "tolerance_pp": 25.0},
    "icp_creation_shift": {"min_increase_pp": 0.0},
    "revenue_concentration": {"top_n": 50, "min_top_share_pct": 10.0},
}


def make_opp(n_per_q=300, seed=1, account_segments=None):
    """Synthetic workbook rows with controllable pathologies.

    account_segments: optional {account_id: segment} mapping - the engine
    denormalizes segment onto facts, so checks may rely on it.
    """
    nprng = np.random.default_rng(seed)
    # separate stream so adding durations doesn't shift the fixture's
    # established randomness (win-rate bands etc.)
    dur_rng = np.random.default_rng(seed + 999)
    icp_rng = np.random.default_rng(seed + 555)
    quarters = ["FY26-Q1", "FY26-Q2", "FY26-Q3", "FY26-Q4"]
    q_ends = {"FY26-Q1": "2026-03-31", "FY26-Q2": "2026-06-30",
              "FY26-Q3": "2026-09-30", "FY26-Q4": "2026-12-31"}
    regions = ["AMER", "EMEA", "APAC"]
    base = {"AMER": [12, 14, 15.5, 15.5], "APAC": [12, 14, 15.5, 15.5],
            "EMEA": [11.5, 13.5, 21, 22]}
    rows = []
    for qi, label in enumerate(quarters):
        q_end = pd.Timestamp(q_ends[label])
        q_start = q_end - pd.DateOffset(months=3) + pd.Timedelta(days=1)
        q_len = (q_end - q_start).days + 1
        for _ in range(n_per_q):
            region = regions[nprng.integers(0, 3)]
            day = int(nprng.integers(1, q_len + 1))
            disc = base[region][qi] + nprng.normal(0, 3)
            if day > q_len - 14:
                disc += 6.5
            disc = float(np.clip(disc, 0, 40))
            list_price = round(float(nprng.lognormal(10.7, 0.8)), 2)
            account_id = f"ACC-{nprng.integers(1, 61):04d}"
            close_date = q_start + pd.Timedelta(days=day - 1)
            created_date = close_date - pd.Timedelta(
                days=int(dur_rng.integers(30, 60)))
            rows.append({
                "fiscal_quarter": label,
                "region": region,
                "account_id": account_id,
                "segment": (account_segments or {}).get(account_id,
                                                        "Enterprise"),
                "icp": bool(icp_rng.random() < 0.4),
                "close_date": close_date,
                "created_date": created_date,
                "stage": "Closed Won" if nprng.random() < 0.27 else "Closed Lost",
                "list_price": list_price,
                "discount_pct": round(disc, 2),
                "realized_price": round(list_price * (1 - disc / 100), 2),
            })
    return pd.DataFrame(rows)


def make_accounts():
    rng = np.random.default_rng(2)
    segments = ["Enterprise", "Mid-Market", "SMB"]
    return pd.DataFrame({
        "account_id": [f"ACC-{i + 1:04d}" for i in range(60)],
        "region": [rng.choice(["AMER", "EMEA", "APAC"]) for _ in range(60)],
        "segment": [rng.choice(segments) for _ in range(60)],
    })


@pytest.fixture(scope="module")
def good_data():
    accounts = make_accounts()
    seg_map = dict(zip(accounts["account_id"], accounts["segment"]))
    opp = make_opp(account_segments=seg_map)
    return opp, accounts


def run_check(name, opp, accounts):
    params = dict(CRITERIA_PARAMS[name])
    if name == "revenue_vs_plan":
        # plan targets derived from the data itself: the fixture proves the
        # check's arithmetic, not raking (covered in test_planning.py).
        # opp already carries denormalized segment (engine contract).
        won = opp[opp["stage"] == "Closed Won"]
        agg = (won.groupby(["segment", "fiscal_quarter"])["realized_price"]
               .sum().reset_index())
        agg.columns = ["segment", "fiscal_quarter", "target_realized_usd"]
        params["_quota_df"] = agg
    return CHECKS[name](opp, accounts, params)


def test_good_data_passes_all_checks(good_data):
    opp, accounts = good_data
    for name in CHECKS:
        r = run_check(name, opp, accounts)
        assert r["ok"], f"{name} should pass on story-shaped data: {r['detail']}"
        assert r["margin"] > 0, f"{name} passing but margin not positive: {r['margin']}"


def test_flat_discounts_fail_discount_checks(good_data):
    opp, accounts = good_data
    broken = opp.copy()
    won = broken["stage"] == "Closed Won"
    broken.loc[won, "discount_pct"] = 15.0
    list_p = broken.loc[won, "list_price"]
    broken.loc[won, "realized_price"] = (list_p * 0.85).round(2)
    for name in ("avg_discount_quarter", "region_discount_premium", "end_of_quarter_effect"):
        r = run_check(name, broken, accounts)
        assert not r["ok"] and r["margin"] < 0, f"{name} should fail on flat discounts"


def test_broken_winrate_fails_flat_check(good_data):
    opp, accounts = good_data
    broken = opp.copy()
    rates = {"FY26-Q1": 0.15, "FY26-Q2": 0.40, "FY26-Q3": 0.20, "FY26-Q4": 0.35}
    for label, rate in rates.items():
        m = broken["fiscal_quarter"] == label
        idx = broken.index[m].to_numpy()
        n_won = int(round(len(idx) * rate))
        stages = np.array(["Closed Lost"] * len(idx), dtype=object)
        stages[:n_won] = "Closed Won"
        broken.loc[idx, "stage"] = stages
    r = run_check("win_rate_flat", broken, accounts)
    assert not r["ok"], "win rate check must catch quarter outliers"


def test_no_emea_premium_fails_region_check(good_data):
    opp, accounts = good_data
    broken = opp.copy()
    won = broken["stage"] == "Closed Won"
    amer_avg_q = broken[won & (broken["region"] == "AMER")].groupby("fiscal_quarter")["discount_pct"].mean()
    emea = won & (broken["region"] == "EMEA")
    broken.loc[emea, "discount_pct"] = broken.loc[emea, "fiscal_quarter"].map(amer_avg_q)
    r = run_check("region_discount_premium", broken, accounts)
    assert not r["ok"], "region premium check must fail without EMEA premium"


def test_sanity_violations_fail_sanity_check(good_data):
    opp, accounts = good_data
    broken = opp.copy()
    broken.loc[broken.index[0], "realized_price"] = -100.0
    broken.loc[broken.index[1], "account_id"] = "ACC-9999"
    r = run_check("data_sanity", broken, accounts)
    assert not r["ok"] and r["margin"] < 0
    assert "non-positive" in r["detail"] and "orphan" in r["detail"]


def test_margins_rank_distance_to_threshold(good_data):
    """Margin semantics: bigger margin = safer. A barely-passing config has smaller margin."""
    opp, accounts = good_data
    tight = CHECKS["win_rate_flat"](opp, accounts, {"band_pp": 2.5})
    loose = CHECKS["win_rate_flat"](opp, accounts, {"band_pp": 6.0})
    assert loose["margin"] > tight["margin"]
    assert tight["margin"] == pytest.approx(loose["margin"] - 3.5)
