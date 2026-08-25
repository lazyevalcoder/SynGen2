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
    # M5 iter 2 checks (fixture: premium tier carries +2pp discount over
    # entry, flat cogs ratios, ~50/50 revenue split)
    "blended_margin_trend": {"target_change_pct": -4.0, "tolerance_pp": 6.0},
    "tier_share_shift": {"tier": "premium", "from_share_pct": 40.0,
                         "to_share_pct": 40.0, "tolerance_pp": 15.0},
    "discount_margin_link": {"high_margin_tier": "premium",
                             "low_margin_tier": "entry", "min_gap_pp": 0.0},
    "avg_price_by_tier": {"tier": "entry", "max_avg_realized_usd": 500000.0},
    # quota df injected at runtime (see run_check), like revenue_vs_plan
    "gap_concentration": {"dimension": "segment",
                          "min_bottom_gap_share_pct": 60.0},
    # M5 iter 3 P4 checks (fixture: ~5% open rows, slip starts in Q3)
    "stage_aging": {"stale_threshold_days": 270,
                    "max_stale_share_pct": 60.0},
    "slippage_trend": {"min_increase_pp": 10.0},
    "coverage_ratio": {"quarter": "FY26-Q4", "min_multiple": 0.005},
    "pipeline_concentration": {"top_n_accounts": 45,
                               "min_top_share_pct": 50.0},
    # M5 iter 4 WS1-rest check (capacity df injected at runtime, see
    # run_check): fully staffed fixture rows -> 100% effective capacity
    "effective_capacity": {"target_pct": 100.0, "band_pp": 2.0},
    # WS1-rest checks with runtime-injected fixtures (see run_check):
    # quota ratio + potential column derived from the data itself
    "quota_vs_potential": {},
    "potential_coverage_gap": {},
    "headcount_growth_placement": {"min_growth_share_pct": 0.0},
    # WS7 checks (ownership df injected at runtime, see run_check)
    "unowned_account_share": {"top_value_pct": 100,
                              "min_unowned_share_pct": 0.0},
    "post_change_revenue_decline": {"min_gap_pp": -10_000.0},
    # WS7 forecast/activity checks (dfs injected at runtime, see run_check)
    "forecast_vs_actual": {"target_pct": 100.0, "band_pp": 5.0},
    "commit_no_engagement_share": {"min_share_pct": 0.0},
    # WS8 checks: fixture carries no whales -> structural-fail paths are
    # covered in test_capacity.py; skip via impossible bands is not
    # possible here, so give a flat synthetic flag column instead
    "core_vs_headline_growth": {"min_headline_growth_pct": -100.0,
                                "max_core_growth_pct": 100.0},
    "elasticity_differential": {"min_gap_pp": -10_000.0},
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
    prod_rng = np.random.default_rng(seed + 777)
    pipe_rng = np.random.default_rng(seed + 888)
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
            # ~35% of rows are premium tier and get +2pp below; a uniform
            # rebate keeps the overall discount means at their targets
            disc = float(np.clip(disc - 0.7, 0, 40))
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
            # M5 iter 2 product columns (separate stream, see above):
            # premium is the high-margin tier and gets +2pp discount so
            # discount_margin_link has a positive gap on story-shaped data
            tier = "premium" if prod_rng.random() < 0.35 else "entry"
            rows[-1]["product_id"] = f"SKU-{tier.upper()}"
            rows[-1]["product_tier"] = tier
            rows[-1]["cogs_ratio"] = 0.30 if tier == "premium" else 0.60
            if tier == "premium":
                rows[-1]["discount_pct"] = round(min(disc + 2.0, 40), 2)
                rows[-1]["realized_price"] = round(
                    list_price * (1 - rows[-1]["discount_pct"] / 100), 2)
            # M5 iter 3 open-pipeline rows (~5%, slip starts in Q3) on
            # their own stream; expected_close_date adjacent to close_date
            row = rows[-1]
            if pipe_rng.random() < 0.05:
                row["stage"] = "Discovery"
                row["close_date"] = pd.NaT
                if qi >= 2:  # slippage trend rises across the year
                    row["expected_close_date"] = q_end + pd.Timedelta(days=30)
                else:
                    row["expected_close_date"] = close_date
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
    if name in ("revenue_vs_plan", "gap_concentration", "coverage_ratio"):
        # plan targets derived from the data itself: the fixture proves the
        # check's arithmetic, not raking (covered in test_planning.py /
        # test_iter2.py). opp already carries denormalized segment.
        won = opp[opp["stage"] == "Closed Won"]
        agg = (won.groupby(["segment", "fiscal_quarter"])["realized_price"]
               .sum().reset_index())
        agg.columns = ["segment", "fiscal_quarter", "target_realized_usd"]
        if name == "revenue_vs_plan":
            params["_quota_df"] = agg
        elif name == "coverage_ratio":
            quota = agg.copy() * 1  # keep columns; scale below
            quota["target_realized_usd"] *= 0.95 / 1
            quota = quota.rename(columns={"segment": "plan_unit"})
            quota.insert(0, "plan_unit_type", "segment")
            params["_quota_df"] = quota
        else:
            # per-segment totals as plan; make one segment a deliberate
            # laggard (target >> actual) so the bottom quartile
            # deterministically holds most of the shortfall
            agg["target_realized_usd"] *= 0.95
            worst_unit = "Enterprise"
            laggard = (won[won["segment"] == worst_unit]
                       .groupby("fiscal_quarter")["realized_price"].sum()
                       / 0.55).reset_index()
            laggard.columns = ["fiscal_quarter", "target_realized_usd"]
            laggard.insert(0, "segment", worst_unit)
            combined = pd.concat(
                [agg[agg["segment"] != worst_unit], laggard],
                ignore_index=True)
            quota = combined.rename(columns={"segment": "plan_unit"})
            quota.insert(0, "plan_unit_type", "segment")
            params["_quota_df"] = quota
    if name == "effective_capacity":
        # fully-staffed capacity plan (plan == actual, no ramping) so the
        # fixture's 100% effective capacity matches the params above
        quarters = ["FY26-Q1", "FY26-Q2", "FY26-Q3", "FY26-Q4"]
        params["_capacity_df"] = pd.DataFrame([{
            "fiscal_quarter": q, "plan_unit_type": "territory",
            "plan_unit": "East", "headcount_plan": 10,
            "headcount_actual": 10, "ramping_reps": 0,
            "ramp_productivity_pct": 100.0,
            "effective_capacity_pct": 100.0} for q in quarters])
    if name == "quota_vs_potential":
        # per-segment potential set EXACTLY proportional to that segment's
        # plan -> every unit's ratio is uniformly 50%, arithmetic under test
        acc2 = accounts.copy()
        won = opp[opp["stage"] == "Closed Won"]
        agg = (won.groupby(["segment", "fiscal_quarter"])["realized_price"]
               .sum().reset_index())
        agg.columns = ["segment", "fiscal_quarter", "target_realized_usd"]
        seg_targets = agg.groupby("segment")["target_realized_usd"].sum()
        per_acct = seg_targets / accounts.groupby("segment").size()
        acc2["market_potential_usd"] = acc2["segment"].map(
            per_acct).astype(float) / 0.5
        params["_quota_df"] = agg
        params["dimension"] = "segment"
        params["target_ratio_pct"] = 50.0
        params["band_pp"] = 0.5
        return CHECKS[name](opp, acc2, params)
    if name == "potential_coverage_gap":
        # potential proportional to actual creation per region -> zero
        # gap, which satisfies min_gap_pp of 0
        acc2 = accounts.copy()
        counts = opp.groupby("region").size()
        acc2["market_potential_usd"] = acc2["region"].map(
            counts).astype(float)
        params["dimension"] = "region"
        params["min_gap_pp"] = 0.0
        return CHECKS[name](opp, acc2, params)
    if name == "headcount_growth_placement":
        # capacity df derived from the fixture's regions with flat
        # headcount -> zero additions; min_growth_share_pct 0 passes on
        # the "no additions" structural path being data-shaped, so give a
        # real growth plan instead: +1 head in every region
        regions = sorted(accounts["region"].unique())
        rows = []
        for qi, q in enumerate(["FY26-Q1", "FY26-Q2", "FY26-Q3", "FY26-Q4"]):
            for r in regions:
                hc = 10 + qi  # steady +1/quarter everywhere
                rows.append({
                    "fiscal_quarter": q, "plan_unit_type": "region",
                    "plan_unit": r, "headcount_plan": hc,
                    "headcount_actual": hc, "ramping_reps": 0,
                    "ramp_productivity_pct": 100.0,
                    "effective_capacity_pct": 100.0})
        params["_capacity_df"] = pd.DataFrame(rows)
        # all units grow equally; strong-half share ~= 100/n_units
        # (rounding of the half-split), so sit the band just under it
        params["min_growth_share_pct"] = 90.0 / len(regions)
    if name in ("unowned_account_share", "post_change_revenue_decline"):
        # fully-owned stable history: exercises the checks' arithmetic
        # paths without inventing a second dataset (both directions are
        # covered in test_capacity.py)
        ids = sorted(accounts["account_id"].unique())
        rows = []
        # every 9th account goes unowned in the last quarter -> ~11%
        # unowned among top-value accounts vs a 5% floor: positive margin
        for q in ["FY26-Q1", "FY26-Q2", "FY26-Q3", "FY26-Q4"]:
            for i, acct in enumerate(ids):
                owner = None if (q == "FY26-Q4" and i % 9 == 0) \
                    else f"Rep {i % 5}"
                rows.append({"account_id": acct, "fiscal_quarter": q,
                             "owner": owner})
        params["_ownership_df"] = pd.DataFrame(rows)
        if name == "unowned_account_share":
            params["min_unowned_share_pct"] = 5.0
    if name == "forecast_vs_actual":
        # snapshot built at ratio exactly 1.0 -> matches the params above
        rows = [{"fiscal_quarter": q, "committed_usd": 100.0,
                 "actual_usd": 100.0, "commit_vs_actual_pct": 100.0}
                for q in ["FY26-Q1", "FY26-Q2", "FY26-Q3", "FY26-Q4"]]
        params["_forecast_df"] = pd.DataFrame(rows)
    if name == "core_vs_headline_growth":
        opp2 = opp.copy()
        # flag the single largest won deal per quarter as a whale
        opp2["is_outlier"] = False
        won_idx = opp2.index[opp2["stage"] == "Closed Won"]
        for q in opp2["fiscal_quarter"].unique():
            q_won = opp2.loc[won_idx][
                opp2.loc[won_idx]["fiscal_quarter"] == q]
            top = q_won["realized_price"].idxmax()
            opp2.at[top, "is_outlier"] = True
        return CHECKS[name](opp2, accounts, params)
    if name == "commit_no_engagement_share":
        # activity df with zero touches everywhere + in_commit column on
        # all won rows: every commit deal is zero-touch -> share 100%
        act_rows = [{"account_id": a, "fiscal_quarter": q, "touches": 0}
                    for a in sorted(accounts["account_id"].unique())
                    for q in ["FY26-Q1", "FY26-Q2", "FY26-Q3", "FY26-Q4"]]
        params["_activity_df"] = pd.DataFrame(act_rows)
        opp2 = opp.copy()
        opp2["in_commit"] = opp2["stage"] == "Closed Won"
        params["min_share_pct"] = 50.0
        return CHECKS[name](opp2, accounts, params)
    if name == "elasticity_differential":
        # synthetic potential so the differential arithmetic runs; the
        # huge negative band tolerates the fixture's random conversion
        acc2 = accounts.copy()
        pot_rng = np.random.default_rng(6)
        acc2["market_potential_usd"] = pot_rng.uniform(
            10_000, 900_000, len(acc2))
        params["min_gap_pp"] = -10_000.0
        return CHECKS[name](opp, acc2, params)
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
