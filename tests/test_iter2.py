"""M5 iteration 2: products/margins (WS2), correlation (WS4), territories
and full planning dimension (WS5). Every extension tested in BOTH
directions: present-and-passing and absent/anti-config-failing. Golden
anchor rule: without a products block or territories the engine output
must be byte-identical to pre-iter-2 behavior."""
import copy

import numpy as np
import pandas as pd
import pytest

from syngen.config import ConfigError, validate_simulator_doc
from syngen.generator.engine import build_accounts, build_opportunities, \
    apply_raking, build_quota_plan
from syngen.validator import checks


def base_cfg(**over):
    over = copy.deepcopy(over)  # never share mutable fixtures across tests
    cfg = {
        "seed": 42,
        "time_model": {
            "fiscal_year": "FY26",
            "quarter_labels": ["FY26-Q1", "FY26-Q2", "FY26-Q3", "FY26-Q4"],
            "quarter_end_dates": ["2026-03-31", "2026-06-30",
                                  "2026-09-30", "2026-12-31"],
        },
        "output": {"workbook": "out/x.xlsx"},
        "accounts": {
            "count": 60,
            "regions": {"AMER": 0.5, "EMEA": 0.3, "APAC": 0.2},
            "segments": {"Enterprise": 0.4, "Mid-Market": 0.35, "SMB": 0.25},
            "industries": ["Tech", "Retail"],
        },
        "opportunities": {
            "per_quarter": 120,
            "win_rate": 0.3,
            "win_rate_jitter": 0.02,
            "owners": ["A", "B"],
            "deal_duration_days": [20, 40],
            "close_clustering": {"share_in_end_of_quarter_window": 0.25},
            "deal_size_lognormal": {"median_usd": 40000, "sigma": 0.6},
            "discount": {
                "base_by_quarter": {
                    "AMER": [10, 10, 10, 10],
                    "EMEA": [12, 12, 12, 12],
                    "APAC": [14, 14, 14, 14]},
                "noise_sd_pp": 2.5,
                "end_of_quarter_boost_pp": 6,
                "end_of_quarter_window_days": 10,
                "min_pct": 0, "max_pct": 35},
        },
    }
    cfg.update(over)
    return validate_simulator_doc(cfg)


PRODUCTS = {
    "catalog": [
        {"id": "CORE-1", "tier": "core", "share": 0.6},
        {"id": "ENTRY-1", "tier": "entry", "share": 0.3},
        {"id": "PREM-1", "tier": "premium", "share": 0.1},
    ],
    "margin_by_tier": {"entry": 0.45, "core": 0.6, "premium": 0.75},
}


def test_products_absent_output_unchanged():
    """Golden-anchor safety: no products block -> no new columns."""
    cfg = base_cfg()
    acc = build_accounts(cfg, np.random.default_rng(cfg["seed"]))
    opp = build_opportunities(cfg, acc, np.random.default_rng(cfg["seed"]))
    for col in ("product_id", "product_tier", "cogs_ratio", "territory"):
        assert col not in opp.columns
        assert col not in acc.columns


def test_products_attribution_deterministic_and_tiered():
    cfg = base_cfg(products=PRODUCTS)
    acc = build_accounts(cfg, np.random.default_rng(cfg["seed"]))
    o1 = build_opportunities(cfg, acc, np.random.default_rng(cfg["seed"]))
    o2 = build_opportunities(cfg, acc, np.random.default_rng(cfg["seed"]))
    pd.testing.assert_frame_equal(o1, o2)  # named stream => reproducible
    assert set(o1["product_id"].unique()) <= {p["id"] for p in PRODUCTS["catalog"]}
    tiers = dict(zip([p["id"] for p in PRODUCTS["catalog"]],
                     [p["tier"] for p in PRODUCTS["catalog"]]))
    assert all(tiers[r.product_id] == r.product_tier
               for r in o1.itertuples())
    # cogs_ratio = 1 - margin_at_list
    assert ((o1["cogs_ratio"] > 0) & (o1["cogs_ratio"] < 1)).all()


def test_identity_holds_with_tier_pricing_and_discount_coupling():
    prods = copy.deepcopy(PRODUCTS)
    prods["price_multiplier_by_tier"] = {"entry": 0.4, "core": 1.0,
                                         "premium": 2.2}
    prods["discount_delta_pp_by_tier"] = {"premium": 5}
    cfg = base_cfg(products=prods)
    acc = build_accounts(cfg, np.random.default_rng(cfg["seed"]))
    opp = build_opportunities(cfg, acc, np.random.default_rng(cfg["seed"]))
    # derived-field identity survives tier pricing + discount coupling
    expect = (opp["list_price"] * (1 - opp["discount_pct"] / 100)).round(2)
    assert np.allclose(expect, opp["realized_price"])
    prem = opp[opp["product_tier"] == "premium"]
    core = opp[opp["product_tier"] == "core"]
    if len(prem) and len(core):
        assert prem["discount_pct"].mean() > core["discount_pct"].mean()


def test_raking_preserves_margin_pct():
    """Margin fields are scale-invariant under monetary raking."""
    prods = copy.deepcopy(PRODUCTS)
    prods["price_multiplier_by_tier"] = {"entry": 0.5, "premium": 2.0}
    cfg = base_cfg(products=prods, quota={
        "by_segment": {"Enterprise": [1_000_000] * 4,
                       "Mid-Market": [700_000] * 4, "SMB": [400_000] * 4},
        "attainment_by_segment": {"Enterprise": 0.9}})
    acc = build_accounts(cfg, np.random.default_rng(cfg["seed"]))
    opp = build_opportunities(cfg, acc, np.random.default_rng(cfg["seed"]))
    m_before = checks._margin_pct(opp[opp["stage"] == "Closed Won"]).mean()
    raked = apply_raking(opp, cfg)
    m_after = checks._margin_pct(raked[raked["stage"] == "Closed Won"]).mean()
    assert abs(m_before - m_after) < 0.05
    expect = (raked["list_price"] * (1 - raked["discount_pct"] / 100)).round(2)
    assert np.allclose(expect, raked["realized_price"])


def test_cogs_inflation_erodes_margin():
    prods = copy.deepcopy(PRODUCTS)
    prods["cogs_inflation_by_quarter"] = [1.0, 1.03, 1.06, 1.09]
    cfg = base_cfg(products=prods, seed=7)
    acc = build_accounts(cfg, np.random.default_rng(cfg["seed"]))
    opp = build_opportunities(cfg, acc, np.random.default_rng(cfg["seed"]))
    won = opp[opp["stage"] == "Closed Won"]
    q1 = won[won["fiscal_quarter"] == "FY26-Q1"]
    q4 = won[won["fiscal_quarter"] == "FY26-Q4"]
    assert q4["cogs_ratio"].mean() > q1["cogs_ratio"].mean() * 1.05


# --- check functions ------------------------------------------------------

def make_opp_with_tiers(shares=(0.25, 0.25), discounts=(10.0, 30.0),
                        n=200, prices=(50000, 10000)):
    rows = []
    for qi, label in enumerate(["FY26-Q1", "FY26-Q2"]):
        for i in range(n):
            tier = "premium" if i % 2 else "entry"
            k = 0 if tier == "premium" else 1
            rows.append({
                "fiscal_quarter": label,
                "stage": "Closed Won",
                "segment": "SMB",
                "product_id": f"P-{tier}",
                "product_tier": tier,
                "cogs_ratio": 0.25 if tier == "premium" else 0.55,
                "discount_pct": discounts[k] * (1.3 ** qi),
                "list_price": prices[k],
                "realized_price": round(prices[k]
                                        * (1 - discounts[k] * (1.3 ** qi)
                                           / 100), 2),
            })
    return pd.DataFrame(rows)


PARAMS = {"quarter_ends": {"FY26-Q1": "2026-03-31", "FY26-Q2": "2026-06-30"}}


def test_blended_margin_trend_both_directions():
    opp = make_opp_with_tiers(discounts=(15.0, 15.0))
    up = checks.check_blended_margin_trend(
        opp, None, {**PARAMS, "target_change_pct": 0, "tolerance_pp": 2})
    assert up["ok"], up
    down = checks.check_blended_margin_trend(
        opp, None, {**PARAMS, "target_change_pct": -8, "tolerance_pp": 1})
    assert not down["ok"]
    # structural without products
    plain = opp.drop(columns=["product_tier", "cogs_ratio"])
    r = checks.check_blended_margin_trend(
        plain, None, {**PARAMS, "target_change_pct": 0, "tolerance_pp": 2})
    assert r.get("structural") is True


def test_discount_margin_link_both_directions():
    linked = make_opp_with_tiers(discounts=(30.0, 8.0))  # premium discounted more
    ok = checks.check_discount_margin_link(linked, None, {
        "high_margin_tier": "premium", "low_margin_tier": "entry",
        "min_gap_pp": 15})
    assert ok["ok"], ok
    bad = checks.check_discount_margin_link(linked, None, {
        "high_margin_tier": "premium", "low_margin_tier": "entry",
        "min_gap_pp": 40})
    assert not bad["ok"]
    inverted = make_opp_with_tiers(discounts=(8.0, 30.0))
    anti = checks.check_discount_margin_link(inverted, None, {
        "high_margin_tier": "premium", "low_margin_tier": "entry",
        "min_gap_pp": 5})
    assert not anti["ok"]


def test_avg_price_by_tier():
    opp = make_opp_with_tiers(prices=(50000, 8000))
    ok = checks.check_avg_price_by_tier(
        opp, None, {"tier": "entry", "max_avg_realized_usd": 10000})
    assert ok["ok"], ok
    tight = checks.check_avg_price_by_tier(
        opp, None, {"tier": "entry", "max_avg_realized_usd": 4000})
    assert not tight["ok"]
    missing = checks.check_avg_price_by_tier(
        opp, None, {"tier": "mid", "max_avg_realized_usd": 99999})
    assert missing.get("structural") is True


def test_gap_concentration_territory():
    quota = pd.DataFrame([
        {"plan_unit_type": "territory", "plan_unit": t,
         "fiscal_quarter": q, "target_realized_usd": 100000}
        for t in ["West", "East", "North", "South"]
        for q in ["FY26-Q1", "FY26-Q2"]])
    # West badly misses; East/North beat plan; South roughly on plan
    attainments = {"West": 0.30, "East": 1.05, "North": 1.02, "South": 0.98}
    rows = [{"fiscal_quarter": "FY26-Q1", "stage": "Closed Won",
             "territory": unit, "segment": "SMB",
             "realized_price": round(200000 * a, 2)}
            for unit, a in attainments.items()]
    opp = pd.DataFrame(rows)
    params = {**PARAMS, "_quota_df": quota, "dimension": "territory",
              "min_bottom_gap_share_pct": 80}
    ok = checks.check_gap_concentration(opp, None, params)
    assert ok["ok"], ok
    strict = checks.check_gap_concentration(
        opp, None, {**params, "min_bottom_gap_share_pct": 99})
    assert not strict["ok"]
    no_quota = checks.check_gap_concentration(
        opp, None, {"quarter_ends": PARAMS["quarter_ends"],
                    "dimension": "territory",
                    "min_bottom_gap_share_pct": 50})
    assert no_quota.get("structural") is True


def test_revenue_vs_plan_unified_schema_territory():
    quota = pd.DataFrame([
        {"plan_unit_type": "territory", "plan_unit": "West",
         "fiscal_quarter": "FY26-Q1", "target_realized_usd": 100000}])
    opp = pd.DataFrame([{"fiscal_quarter": "FY26-Q1", "stage": "Closed Won",
                         "territory": "West", "realized_price": 97000}])
    r = checks.check_revenue_vs_plan(opp, None, {
        "quarter_ends": PARAMS["quarter_ends"], "_quota_df": quota,
        "segment": "West", "dimension": "territory", "target_pct": 97,
        "band_pct": 1})
    assert r["ok"], r
    wrong_unit = checks.check_revenue_vs_plan(opp, None, {
        "quarter_ends": PARAMS["quarter_ends"], "_quota_df": quota,
        "segment": "East", "dimension": "territory", "target_pct": 97,
        "band_pct": 1})
    assert not wrong_unit["ok"] and wrong_unit.get("structural")


def test_tier_share_shift_both_directions():
    def shifted_opp(q1_entry, q2_entry):
        rows = []
        for label, entry_share in (("FY26-Q1", q1_entry),
                                   ("FY26-Q2", q2_entry)):
            for i in range(100):
                tier = "entry" if i < entry_share else "premium"
                price = 10000 if tier == "entry" else 90000  # revenue-weighted
                rows.append({
                    "fiscal_quarter": label, "stage": "Closed Won",
                    "segment": "SMB", "product_tier": tier,
                    "cogs_ratio": 0.5, "list_price": price,
                    "realized_price": price * 0.9})
        return pd.DataFrame(rows)

    opp = shifted_opp(10, 60)  # entry revenue share rises sharply
    ok = checks.check_tier_share_shift(opp, None, {
        "quarter_ends": PARAMS["quarter_ends"], "tier": "entry",
        "from_share_pct": 1, "to_share_pct": 15, "tolerance_pp": 2})
    assert ok["ok"], ok
    anti = checks.check_tier_share_shift(opp, None, {
        "quarter_ends": PARAMS["quarter_ends"], "tier": "entry",
        "from_share_pct": 15, "to_share_pct": 1, "tolerance_pp": 2})
    assert not anti["ok"]


# --- config validation ----------------------------------------------------

def test_validation_products_errors():
    with pytest.raises(ConfigError):  # margin missing for a tier
        base_cfg(products={"catalog": [{"id": "A", "tier": "core",
                                        "share": 1.0}]})
    bad = copy.deepcopy(PRODUCTS)
    bad["price_multiplier_by_tier"] = {"ghost": 2.0}
    with pytest.raises(ConfigError):
        base_cfg(products=bad)
    bad2 = copy.deepcopy(PRODUCTS)
    bad2["catalog"][0]["share"] = {"weights_by_quarter": [1.0, 1.0]}
    with pytest.raises(ConfigError):
        base_cfg(products=bad2)
    bad3 = copy.deepcopy(PRODUCTS)
    bad3["cogs_inflation_by_quarter"] = [1.0, 0]
    with pytest.raises(ConfigError):
        base_cfg(products=bad3)


def test_validation_quota_dimension_exclusive():
    with pytest.raises(ConfigError):  # both dimensions at once
        base_cfg(quota={
            "by_segment": {"SMB": [100000] * 4},
            "by_territory": {"West": [100000] * 4}})
    with pytest.raises(ConfigError):  # unknown territory
        base_cfg(quota={"by_territory": {"Atlantis": [100000] * 4}})
    with pytest.raises(ConfigError):  # territory block but no mapping
        base_cfg(quota={"by_territory": {"West": [100000] * 4}})


def test_territories_rollup_and_unknown_region():
    cfg = base_cfg(accounts={
        "count": 40,
        "regions": {"AMER": 0.5, "EMEA": 0.5},
        "segments": {"SMB": 1.0},
        "industries": ["Tech"],
        "territories": {"AMER-West": ["AMER"], "EMEA-Core": ["EMEA"]}})
    acc = build_accounts(cfg, np.random.default_rng(cfg["seed"]))
    assert set(acc["territory"]) == {"AMER-West", "EMEA-Core"}
    opp = build_opportunities(cfg, acc, np.random.default_rng(cfg["seed"]))
    assert "territory" in opp.columns
    with pytest.raises(ConfigError):
        base_cfg(accounts={
            "count": 10, "regions": {"AMER": 1.0}, "segments": {"SMB": 1.0},
            "industries": ["T"], "territories": {"X": ["Nowhere"]}})


def test_quota_plan_unified_schema_and_territory_raking():
    cfg = base_cfg(accounts={
        "count": 40, "regions": {"AMER": 0.6, "EMEA": 0.4},
        "segments": {"SMB": 1.0}, "industries": ["Tech"],
        "territories": {"Amer-T": ["AMER"], "Emea-T": ["EMEA"]}},
        quota={"by_territory": {"Amer-T": [300_000] * 4,
                                "Emea-T": [200_000] * 4},
               "attainment": {"Amer-T": 1.1}})
    plan = build_quota_plan(cfg)
    assert list(plan.columns) == ["plan_unit_type", "plan_unit",
                                  "fiscal_quarter", "target_realized_usd"]
    assert set(plan["plan_unit_type"]) == {"territory"}
    acc = build_accounts(cfg, np.random.default_rng(cfg["seed"]))
    opp = build_opportunities(cfg, acc, np.random.default_rng(cfg["seed"]))
    raked = apply_raking(opp, cfg)
    won = raked[(raked["stage"] == "Closed Won")
                & (raked["fiscal_quarter"] == "FY26-Q1")]
    amer = won.loc[won["territory"] == "Amer-T", "realized_price"].sum()
    assert abs(amer - 330_000) < 1.0  # 110% of 300k, exact to the cent-ish


# --- convergence-loop robustness (live s3/s8 lessons) ----------------------

def test_apply_changes_rejects_invalid_config_wholesale():
    """Live s3 lesson: proposer wrote a per-quarter LIST into attainment
    (scalar expected); raking crashed mid-session. The patch must be
    validated and rejected whole, leaving cfg untouched."""
    from syngen.phases.converge import _apply_changes
    cfg = base_cfg(quota={"by_segment": {"SMB": [100_000] * 4},
                          "attainment_by_segment": {"SMB": 1.0}})
    before = copy.deepcopy(cfg)
    applied = _apply_changes(cfg, [
        {"path": "quota.attainment_by_segment.SMB",
         "to": [1.04, 1.02, 1.0, 0.98]},
    ])
    assert "error" in applied[0]
    assert "invalid" in applied[0]["error"]
    assert cfg == before  # wholesale revert, no partial mutation

    # valid scalar still applies
    ok = _apply_changes(cfg, [
        {"path": "quota.attainment_by_segment.SMB", "to": 0.97}])
    assert "error" not in ok[0]
    assert cfg["quota"]["attainment_by_segment"]["SMB"] == 0.97


def test_apply_changes_rejects_unknown_product_tier_reference():
    from syngen.phases.converge import _apply_changes
    cfg = base_cfg(products=PRODUCTS)
    before = copy.deepcopy(cfg)
    applied = _apply_changes(cfg, [
        {"path": "products.margin_by_tier", "to":
            {"entry": 0.45, "core": 0.6}},  # drops 'premium' -> invalid
    ])
    assert "error" in applied[0]
    assert cfg == before


def test_apply_changes_renormalizes_near_miss_share_sums():
    """Live s12 lesson: one-tier share edits left siblings summing to 1.09
    and whole proposals were rejected. Shares are relative weights - a
    near-miss sum is renormalized instead of failing the proposal."""
    from syngen.phases.converge import _apply_changes
    prods = copy.deepcopy(PRODUCTS)
    prods["catalog"] = [
        {"id": "E", "tier": "entry",
         "share": {"weights_by_quarter": [0.3, 0.3, 0.3, 0.3]}},
        {"id": "C", "tier": "core",
         "share": {"weights_by_quarter": [0.5, 0.5, 0.5, 0.5]}},
        {"id": "P", "tier": "premium", "share": 0.2},
    ]
    cfg = base_cfg(products=prods)
    applied = _apply_changes(cfg, [
        {"path": "products.catalog[0].share.weights_by_quarter[0]",
         "to": 0.39},  # Q1 now sums to 1.09
    ])
    assert all("error" not in a for a in applied), applied
    q1 = (cfg["products"]["catalog"][0]["share"]["weights_by_quarter"][0]
          + cfg["products"]["catalog"][1]["share"]["weights_by_quarter"][0]
          + 0.2)
    assert abs(q1 - 1.0) < 1e-6
