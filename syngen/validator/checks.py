"""Criterion check functions. Each returns a result dict with a numeric margin.

margin > 0  : passing, value is distance from the threshold (bigger = safer)
margin <= 0 : failing, magnitude is distance from passing
Ported from experiments/C_validator/validate.py (Experiment C, gate PASS),
extended with numeric margins per PRD FR6 / Experiment D thin-margin lesson.
"""
import numpy as np
import pandas as pd

QUARTER_ENDS = {
    "FY26-Q1": "2026-03-31",
    "FY26-Q2": "2026-06-30",
    "FY26-Q3": "2026-09-30",
    "FY26-Q4": "2026-12-31",
}


def resolve_quarter_ends(params):
    """Calendar comes from criteria definitions (injected into params by the
    runner); hardcoded FY26 dates are only a fallback. Live diagnosis showed a
    valid-but-different drafted calendar made every check silently wrong."""
    return params.get("quarter_ends") or QUARTER_ENDS


def _result(ok, actual_display, target_display, detail, margin):
    return {
        "ok": bool(ok),
        "actual": actual_display,
        "target": target_display,
        "detail": detail,
        "margin": round(float(margin), 4),
    }


def quarter_start(date_str):
    return pd.Timestamp(date_str) - pd.DateOffset(months=3) + pd.Timedelta(days=1)


def won_deals(opp):
    return opp[opp["stage"] == "Closed Won"]


def check_win_rate_flat(opp, accounts, params):
    rates = {}
    for label in resolve_quarter_ends(params):
        q = opp[opp["fiscal_quarter"] == label]
        closed = q[q["stage"].isin(["Closed Won", "Closed Lost"])]
        rates[label] = (
            len(closed[closed["stage"] == "Closed Won"]) / len(closed) * 100
            if len(closed)
            else 0.0
        )
    mean = np.mean(list(rates.values()))
    devs = {k: abs(v - mean) for k, v in rates.items()}
    worst_label = max(devs, key=devs.get)
    worst = devs[worst_label]
    band = params["band_pp"]
    detail = (
        f"quarters={{{', '.join(f'{k}: {v:.1f}' for k, v in rates.items())}}}, "
        f"mean={mean:.1f}, max dev {worst_label}={worst:.2f}pp"
    )
    return _result(worst <= band, f"{worst:.2f}pp dev ({worst_label})",
                   f"<= {band}pp of mean", detail, band - worst)


def check_avg_discount_quarter(opp, accounts, params):
    won_q = won_deals(opp)
    won_q = won_q[won_q["fiscal_quarter"] == params["quarter"]]
    actual = won_q["discount_pct"].mean()
    target, tol = params["target_pct"], params["tolerance_pp"]
    margin = tol - abs(actual - target)
    detail = f"{params['quarter']} avg discount on {len(won_q)} won deals"
    return _result(margin >= 0, f"{actual:.2f}%", f"{target}% +/-{tol}pp", detail, margin)


def check_discount_trend_monotonic(opp, accounts, params):
    won_q = won_deals(opp)
    avgs = [won_q[won_q["fiscal_quarter"] == q]["discount_pct"].mean()
            for q in resolve_quarter_ends(params)]
    dips = [avgs[i - 1] - avgs[i] for i in range(1, len(avgs))]
    worst_dip = max(dips)
    limit = params["max_dip_pp"]
    trend = " -> ".join(f"{a:.1f}" for a in avgs)
    return _result(worst_dip <= limit, f"{worst_dip:.2f}pp worst dip",
                   f"<= {limit}pp", f"quarterly avgs: {trend}", limit - worst_dip)


def check_region_discount_premium(opp, accounts, params):
    won_q = won_deals(opp)
    h2 = won_q[won_q["fiscal_quarter"].isin(params["quarters"])]
    region_avgs = h2.groupby("region")["discount_pct"].mean()
    prem = params["region"]
    if prem not in region_avgs.index:
        return _result(False, f"region '{prem}' absent", f">= +{params['min_premium_pp']}pp",
                       f"premium region '{prem}' not found in data", -params["min_premium_pp"])
    missing = [r for r in params["vs"] if r not in region_avgs.index]
    present_vs = [r for r in params["vs"] if r in region_avgs.index]
    if not present_vs:
        return _result(False, "no comparison regions present",
                       f">= +{params['min_premium_pp']}pp",
                       f"comparison regions {params['vs']} not found in data",
                       -params["min_premium_pp"])
    gaps = {other: region_avgs[prem] - region_avgs[other] for other in present_vs}
    worst_other = min(gaps, key=gaps.get)
    worst_gap = gaps[worst_other]
    needed = params["min_premium_pp"]
    gap_str = ", ".join(f"vs {k}: {v:+.2f}pp" for k, v in gaps.items())
    note = f" [absent from data, ignored: {missing}]" if missing else ""
    detail = (
        f"H2 avgs: {{{', '.join(f'{r}: {v:.1f}' for r, v in region_avgs.items())}}}; "
        f"{gap_str}{note}"
    )
    return _result(worst_gap >= needed, f"{worst_gap:+.2f}pp vs {worst_other}",
                   f">= +{needed}pp", detail, worst_gap - needed)


def check_end_of_quarter_effect(opp, accounts, params):
    window = params["window_days"]
    eoq_disc, mid_disc = [], []
    for label, end_str in resolve_quarter_ends(params).items():
        q_end = pd.Timestamp(end_str)
        q_start = quarter_start(end_str)
        q_won = won_deals(opp)
        q_won = q_won[q_won["fiscal_quarter"] == label]
        day = (q_won["close_date"] - q_start).dt.days + 1
        q_len = (q_end - q_start).days + 1
        eoq_disc.append(q_won[day > q_len - window]["discount_pct"])
        mid_disc.append(q_won[(day >= 15) & (day <= 74)]["discount_pct"])
    eoq_mean = pd.concat(eoq_disc).mean() if eoq_disc and sum(len(s) for s in eoq_disc) else float("nan")
    mid_mean = pd.concat(mid_disc).mean() if mid_disc and sum(len(s) for s in mid_disc) else float("nan")
    needed = params["min_gap_pp"]
    n_eoq = sum(len(s) for s in eoq_disc)
    n_mid = sum(len(s) for s in mid_disc)
    detail = f"EOQ avg={eoq_mean:.2f}% (n={n_eoq}), mid-quarter avg={mid_mean:.2f}% (n={n_mid})"
    if pd.isna(eoq_mean) or pd.isna(mid_mean):
        empty = "EOQ" if pd.isna(eoq_mean) else "mid-quarter"
        return _result(False, f"no deals in {empty} window",
                       f">= +{needed}pp", detail + " - window/calendar mismatch?",
                       -needed)
    gap = eoq_mean - mid_mean
    return _result(gap >= needed, f"{gap:+.2f}pp gap", f">= +{needed}pp", detail, gap - needed)


def check_realized_vs_list(opp, accounts, params):
    won_q = won_deals(opp)

    def pct_for(label):
        d = won_q[won_q["fiscal_quarter"] == label]
        return d["realized_price"].sum() / d["list_price"].sum() * 100

    start_actual = pct_for(params["quarter_start"])
    end_actual = pct_for(params["quarter_end"])
    tol = params["tolerance_pp"]
    start_margin = tol - abs(start_actual - params["target_start_pct"])
    end_margin = tol - abs(end_actual - params["target_end_pct"])
    margin = min(start_margin, end_margin)
    ok = start_margin >= 0 and end_margin >= 0
    detail = (
        f"{params['quarter_start']}: {start_actual:.2f}% (target {params['target_start_pct']}%), "
        f"{params['quarter_end']}: {end_actual:.2f}% (target {params['target_end_pct']}%)"
    )
    display = f"{start_actual:.1f}% -> {end_actual:.1f}%"
    target_disp = (
        f"{params['target_start_pct']}% -> {params['target_end_pct']}% +/-{tol}pp"
    )
    return _result(ok, display, target_disp, detail, margin)


def check_data_sanity(opp, accounts, params):
    problems = []
    bad_disc = opp[(opp["discount_pct"] < 0) | (opp["discount_pct"] > params["max_discount_pct"])]
    if len(bad_disc):
        problems.append(f"{len(bad_disc)} discounts outside [0,{params['max_discount_pct']}]")
    if (opp["list_price"] <= 0).any() or (opp["realized_price"] <= 0).any():
        problems.append("non-positive amounts present")
    invalid_fk = ~opp["account_id"].isin(set(accounts["account_id"]))
    if invalid_fk.any():
        problems.append(f"{int(invalid_fk.sum())} orphan account_id references")
    out_of_quarter = 0
    for label, end_str in resolve_quarter_ends(params).items():
        q_end = pd.Timestamp(end_str)
        q_start = quarter_start(end_str)
        m = opp["fiscal_quarter"] == label
        bad = m & ((opp["close_date"] < q_start) | (opp["close_date"] > q_end))
        out_of_quarter += int(bad.sum())
    if out_of_quarter:
        problems.append(f"{out_of_quarter} close dates outside their quarter")
    ok = not problems
    detail = "; ".join(problems) if problems else "all constraints satisfied"
    margin = 1.0 if ok else -float(len(problems))
    return _result(ok, "clean" if ok else "violations", "no violations", detail, margin)


def check_revenue_vs_plan(opp, accounts, params):
    """Attainment of a plan unit's quarterly revenue plan (WS3/WS5).

    Reads the workbook's quota_plan sheet (injected into params by the
    runner as '_quota_df'; unified schema: plan_unit_type/plan_unit).
    params['segment'] is the plan unit value; optional params['dimension']
    selects segment (default) or territory plans. "_all_" aggregates every
    row of the requested dimension. Attainment = closed-won realized /
    target * 100 per quarter; worst quarter decides.
    """
    plan = params.get("_quota_df")
    seg = params["segment"]
    band = float(params["band_pct"])
    target_pct = float(params.get("target_pct", 100.0))
    if plan is None or not len(plan):
        r = _result(False, "no quota_plan sheet",
                    f"{target_pct}% +/-{band:g}pp",
                    "criterion requires a quota block in simulator.json",
                    -band)
        r["structural"] = True
        return r
    dim = params.get("dimension")
    if dim and "plan_unit_type" in plan.columns:
        plan = plan[plan["plan_unit_type"] == dim]
    # "_all_" = aggregate attainment: totals across every planned unit
    if seg == "_all_":
        seg_plan = plan.groupby("fiscal_quarter")[
            "target_realized_usd"].sum().reset_index()
        agg_key = "_all_"
    else:
        if "plan_unit" in plan.columns:  # unified schema
            seg_plan = plan[plan["plan_unit"] == seg]
            agg_col = "plan_unit"
        else:  # legacy sheet schema
            seg_plan = plan[plan["segment"] == seg]
            agg_col = "segment"
        known = sorted(plan[agg_col].unique()) if len(plan) else []
        if not len(seg_plan):
            r = _result(False, f"unit '{seg}' absent from plan",
                        f"{target_pct}% +/-{band:g}pp",
                        f"criterion unit '{seg}' not found; "
                        f"plan covers units: {known}", -band)
            r["structural"] = True
            return r
        seg_plan = seg_plan.copy()
        seg_plan[agg_col] = seg
    won_all = won_deals(opp)
    attainments = {}
    unit_col = dim if dim in ("territory",) else "segment"
    for _, row in seg_plan.iterrows():
        label = row["fiscal_quarter"]
        won_q = won_all[won_all["fiscal_quarter"] == label]
        if seg != "_all_" and unit_col in won_all.columns:
            won_q = won_q[won_q[unit_col] == seg]
        actual = won_q["realized_price"].sum()
        plan_target = float(row["target_realized_usd"])
        attainments[label] = (actual / plan_target * 100) if plan_target else float("nan")
    worst_label = min(attainments,
                      key=lambda k: abs(attainments[k] - target_pct))
    worst_dev = abs(attainments[worst_label] - target_pct)
    detail = "; ".join(f"{k}: {v:.2f}% of plan" for k, v in attainments.items())
    display = f"{attainments[worst_label]:.1f}% ({worst_label})"
    target_disp = f"{target_pct:g}% +/-{band:g}pp"
    return _result(worst_dev <= band, display, target_disp,
                   detail, band - worst_dev)


def check_cycle_length_trend(opp, accounts, params):
    """M4 domain B: average won-deal cycle (close - created) must grow by
    at least min_increase_pct from first to last quarter."""
    labels = list(resolve_quarter_ends(params))
    won = won_deals(opp).copy()
    won["cycle_days"] = (won["close_date"] - won["created_date"]).dt.days
    avgs = {label: won[won["fiscal_quarter"] == label]["cycle_days"].mean()
            for label in labels}
    first, last = labels[0], labels[-1]
    if pd.isna(avgs[first]) or pd.isna(avgs[last]):
        return _result(False, "no won deals in boundary quarters",
                       f">= +{params['min_increase_pct']}%",
                       f"cycle avgs: {avgs}", -params["min_increase_pct"])
    growth = (avgs[last] / avgs[first] - 1) * 100
    needed = params["min_increase_pct"]
    trend = " -> ".join(f"{avgs[l]:.0f}d" for l in labels)
    return _result(growth >= needed, f"{growth:+.1f}% cycle growth",
                   f">= +{needed}%", f"avg cycle: {trend}", growth - needed)


def check_creation_volume_trend(opp, accounts, params):
    """M4 domain B: opportunity creation change from first to last quarter
    must land within tolerance of the story's claimed decline."""
    labels = list(resolve_quarter_ends(params))
    counts = {label: int((opp["fiscal_quarter"] == label).sum())
              for label in labels}
    first, last = labels[0], labels[-1]
    if not counts[first]:
        return _result(False, "no opportunities in first quarter",
                       "decline within band", str(counts),
                       -float(params["tolerance_pp"]))
    change = (counts[last] / counts[first] - 1) * 100  # negative = decline
    target_decline = float(params["target_decline_pct"])
    tol = float(params["tolerance_pp"])
    deviation = abs(change + target_decline)  # +20% decline -> change=-20
    detail = (f"created per quarter: "
              + ", ".join(f"{k}: {v}" for k, v in counts.items()))
    display = f"{change:+.1f}% ({first} -> {last})"
    target_disp = f"decline ~{target_decline:g}% +/-{tol:g}pp"
    return _result(deviation <= tol, display, target_disp, detail,
                   tol - deviation)


def check_deal_size_trend(opp, accounts, params):
    """M5: average won-deal size change from first to last quarter must
    land within tolerance of the story's claim (signed; negative = decline)."""
    labels = list(resolve_quarter_ends(params))
    won = won_deals(opp)
    avgs = {label: won[won["fiscal_quarter"] == label]["list_price"].mean()
            for label in labels}
    first, last = labels[0], labels[-1]
    if pd.isna(avgs[first]) or pd.isna(avgs[last]):
        return _result(False, "no won deals in boundary quarters",
                       f"~{params['target_change_pct']}% +/-{params['tolerance_pp']}pp",
                       str(avgs), -float(params["tolerance_pp"]))
    change = (avgs[last] / avgs[first] - 1) * 100
    target = float(params["target_change_pct"])
    tol = float(params["tolerance_pp"])
    deviation = abs(change - target)
    trend = " -> ".join(f"${avgs[l]:,.0f}" for l in labels)
    return _result(deviation <= tol, f"{change:+.1f}% deal size",
                   f"{target:+g}% +/-{tol:g}pp",
                   f"avg won deal size: {trend}", tol - deviation)


def check_icp_creation_shift(opp, accounts, params):
    """M5 (#7): share of created pipeline from NON-ICP accounts must rise
    from the first to the last quarter by at least min_increase_pp."""
    labels = list(resolve_quarter_ends(params))
    if "icp" not in opp.columns:
        r = _result(False, "no icp field", f">= +{params['min_increase_pp']}pp",
                    "config lacks accounts.icp_share", -params["min_increase_pp"])
        r["structural"] = True
        return r
    shares = {}
    for label in labels:
        q = opp[opp["fiscal_quarter"] == label]
        shares[label] = ((~q["icp"]).mean() * 100) if len(q) else float("nan")
    first, last = labels[0], labels[-1]
    shift = shares[last] - shares[first]
    needed = params["min_increase_pp"]
    detail = "; ".join(f"{k}: {v:.1f}% low-ICP" for k, v in shares.items())
    return _result(shift >= needed, f"{shift:+.1f}pp shift",
                   f">= +{needed:g}pp", detail, shift - needed)


def check_revenue_concentration(opp, accounts, params):
    """M5 (#25): top-N won deals' share of closed-won revenue in the last
    quarter must be at least min_top_share_pct - concentration signal."""
    labels = list(resolve_quarter_ends(params))
    last = labels[-1]
    won = won_deals(opp)
    won = won[won["fiscal_quarter"] == last]
    n_top = int(params.get("top_n", 5))
    needed = params["min_top_share_pct"]
    if len(won) < n_top:
        return _result(False, f"only {len(won)} won deals",
                       f"top {n_top} >= {needed}% of revenue",
                       "not enough won deals in last quarter", -needed)
    rev = won["realized_price"]
    top = rev.nlargest(n_top).sum() / rev.sum() * 100
    detail = (f"top {n_top} of {len(won)} won deals = {top:.1f}% of "
              f"{last} realized revenue")
    return _result(top >= needed, f"{top:.1f}% top-{n_top}",
                   f">= {needed}%", detail, top - needed)


# --- M5 iteration 2: products, margins, correlation, territories ----------


def _margin_pct(df):
    """Per-deal gross margin % of realized revenue. COGS is charged on
    list price; discounts come out of margin:
    margin% = 1 - cogs_ratio * list / realized."""
    cost = df["cogs_ratio"] * df["list_price"]
    return (1.0 - cost / df["realized_price"]) * 100.0


def _structural_no_products(what):
    r = _result(False, "no product columns", what,
                "criterion requires a products block in simulator.json "
                "(product_tier/cogs_ratio columns absent)", -1.0)
    r["structural"] = True
    return r


def check_blended_margin_trend(opp, accounts, params):
    """Blended gross margin % of won deals: last-quarter vs first-quarter
    change must match target_change_pct (signed pp) within tolerance_pp.
    Covers COGS-inflation (#8) and comp-driven margin erosion (#12)."""
    if not {"product_tier", "cogs_ratio"}.issubset(opp.columns):
        return _structural_no_products("blended margin trend")
    labels = list(resolve_quarter_ends(params))
    tol = float(params.get("tolerance_pp", 2.0))
    target = float(params["target_change_pct"])
    won = won_deals(opp)
    margins = {}
    for label in labels:
        q = won[won["fiscal_quarter"] == label]
        margins[label] = (
            (q["realized_price"].sum() -
             (q["cogs_ratio"] * q["list_price"]).sum())
            / q["realized_price"].sum() * 100) if len(q) else float("nan")
    first, last = labels[0], labels[-1]
    delta = margins[last] - margins[first]
    detail = "; ".join(f"{k}: {v:.1f}% margin" for k, v in margins.items()) + \
        f"; delta {delta:+.2f}pp"
    ok = abs(delta - target) <= tol
    return _result(ok, f"{delta:+.1f}pp margin change",
                   f"{target:+g}pp +/-{tol:g}pp", detail,
                   tol - abs(delta - target))


def check_tier_share_shift(opp, accounts, params):
    """Share of WON REVENUE held by one product tier: moves from
    from_share_pct (first quarter) to to_share_pct (last quarter),
    each within tolerance_pp of its target."""
    if not {"product_tier", "cogs_ratio"}.issubset(opp.columns):
        return _structural_no_products("tier share shift")
    labels = list(resolve_quarter_ends(params))
    tier = params["tier"]
    from_share = float(params["from_share_pct"])
    to_share = float(params["to_share_pct"])
    tol = float(params.get("tolerance_pp", 3.0))
    won = won_deals(opp)
    shares = {}
    for label, want in ((labels[0], from_share), (labels[-1], to_share)):
        q = won[won["fiscal_quarter"] == label]
        total = q["realized_price"].sum()
        got = q.loc[q["product_tier"] == tier, "realized_price"].sum()
        shares[label] = (got / total * 100) if total else 0.0
        dev = abs(shares[label] - want)
        if dev > tol:
            detail = (f"tier '{tier}' revenue share {shares[label]:.1f}% "
                      f"in {label}, wanted ~{want:g}%")
            return _result(False, f"{shares[label]:.1f}% ({label})",
                           f"~{want:g}% +/-{tol:g}pp", detail, tol - dev)
    detail = "; ".join(f"{k}: {v:.1f}% of revenue"
                       for k, v in shares.items())
    return _result(True,
                   f"{shares[labels[0]]:.1f}% -> {shares[labels[-1]]:.1f}%",
                   f"~{from_share:g}% -> ~{to_share:g}% +/-{tol:g}pp",
                   detail, tol)


def check_discount_margin_link(opp, accounts, params):
    """WS4 correlation primitive made observable: avg discount on the
    high-margin tier minus avg discount on the low-margin tier must be at
    least min_gap_pp (positive gap = richer tiers discounted harder)."""
    if not {"product_tier", "cogs_ratio"}.issubset(opp.columns):
        return _structural_no_products("discount/margin link")
    hi_tier = params["high_margin_tier"]
    lo_tier = params["low_margin_tier"]
    gap_need = float(params["min_gap_pp"])
    won = won_deals(opp)
    hi = won.loc[won["product_tier"] == hi_tier, "discount_pct"]
    lo = won.loc[won["product_tier"] == lo_tier, "discount_pct"]
    if not len(hi) or not len(lo):
        known = sorted(won["product_tier"].dropna().unique())
        r = _result(False, "tier missing",
                    f"gap >= {gap_need}pp",
                    f"tiers {hi_tier}/{lo_tier} not both present; "
                    f"known tiers: {known}", -gap_need)
        r["structural"] = True
        return r
    gap = hi.mean() - lo.mean()
    detail = (f"avg discount {hi_tier}={hi.mean():.2f}% vs "
              f"{lo_tier}={lo.mean():.2f}% -> gap {gap:+.2f}pp over "
              f"{len(hi)}+{len(lo)} won deals")
    return _result(gap >= gap_need, f"{gap:+.1f}pp gap",
                   f">= {gap_need}pp", detail, gap - gap_need)


def check_avg_price_by_tier(opp, accounts, params):
    """Entry-price discipline (#3/#12): average realized price of won
    deals in a tier must stay under max_avg_realized_usd."""
    if "product_tier" not in opp.columns:
        return _structural_no_products("price point by tier")
    tier = params["tier"]
    cap = float(params["max_avg_realized_usd"])
    won = won_deals(opp)
    t = won.loc[won["product_tier"] == tier, "realized_price"]
    if not len(t):
        known = sorted(won["product_tier"].dropna().unique())
        r = _result(False, f"tier '{tier}' has no won deals",
                    f"avg <= ${cap:,.0f}",
                    f"known tiers: {known}", -cap)
        r["structural"] = True
        return r
    avg = t.mean()
    detail = (f"avg realized ${avg:,.0f} across {len(t)} won "
              f"'{tier}' deals")
    return _result(avg <= cap, f"${avg:,.0f}", f"<= ${cap:,.0f}",
                   detail, cap - avg)


def check_gap_concentration(opp, accounts, params):
    """WS5 territory analysis (#18): the bottom quartile of plan units
    (by attainment) must account for at least min_bottom_gap_share_pct of
    the company's total plan shortfall."""
    plan = params.get("_quota_df")
    dim = params.get("dimension", "territory")
    need = float(params["min_bottom_gap_share_pct"])
    if plan is None or not len(plan):
        r = _result(False, "no quota_plan sheet", f">= {need}% of gap",
                    "criterion requires a quota block in simulator.json",
                    -need)
        r["structural"] = True
        return r
    if dim and "plan_unit_type" in plan.columns:
        plan = plan[plan["plan_unit_type"] == dim]
    units = sorted(plan["plan_unit"].unique()) \
        if "plan_unit" in plan.columns else []
    if not units:
        r = _result(False, "no plan units", f">= {need}% of gap",
                    f"no '{dim}' rows in quota_plan", -need)
        r["structural"] = True
        return r
    unit_col = dim if dim in opp.columns else None
    stats = []
    for unit in units:
        prow = plan[plan["plan_unit"] == unit]
        target = float(prow["target_realized_usd"].sum())
        won = won_deals(opp)
        actual = won.loc[won[unit_col] == unit, "realized_price"].sum() \
            if unit_col else won["realized_price"].sum()
        attain = actual / target * 100 if target else float("nan")
        stats.append((unit, attain, max(target - actual, 0.0)))
    total_gap = sum(g for _, _, g in stats)
    stats.sort(key=lambda s: s[1])  # worst attainment first
    n_bottom = max(1, int(np.ceil(len(stats) * 0.25)))
    bottom = stats[:n_bottom]
    share = sum(g for _, _, g in bottom) / total_gap * 100 if total_gap else 0.0
    names = ", ".join(f"{u} ({a:.0f}%)" for u, a, _ in bottom)
    detail = (f"bottom quartile [{names}] holds {share:.1f}% of the "
              f"${total_gap:,.0f} total shortfall")
    return _result(share >= need, f"{share:.1f}% of gap",
                   f">= {need}% in bottom quartile", detail, share - need)


CLOSED_STAGES = {"Closed Won", "Closed Lost"}


def _open_pipeline(opp):
    return opp[~opp["stage"].isin(CLOSED_STAGES)]


def _pipeline_value(df):
    return df["realized_price"].sum()


def check_stage_aging(opp, accounts, params):
    """P4 (#11): share of open pipeline older than stale_threshold_days
    must stay under max_stale_share_pct. Age is measured at the LAST
    quarter end (deterministic evaluation date)."""
    open_rows = _open_pipeline(opp)
    if not len(open_rows):
        r = _result(False, "no open pipeline", f"<= {params['max_stale_share_pct']}% stale",
                    "no open-pipeline rows - is a pipeline block configured?",
                    -1.0)
        r["structural"] = True
        return r
    labels = list(resolve_quarter_ends(params))
    ref = pd.Timestamp(resolve_quarter_ends(params)[labels[-1]])
    created = pd.to_datetime(open_rows["created_date"])
    age_days = (ref - created).dt.days
    stale = (age_days > float(params["stale_threshold_days"])).mean() * 100
    cap = float(params["max_stale_share_pct"])
    detail = (f"{int((age_days > float(params['stale_threshold_days'])).sum())}"
              f"/{len(open_rows)} open deals older than "
              f"{params['stale_threshold_days']}d at {labels[-1]}")
    return _result(stale <= cap, f"{stale:.1f}% stale",
                   f"<= {cap:g}% stale", detail, cap - stale)


def check_slippage_trend(opp, accounts, params):
    """P4 (#5): share of open deals whose expected close has slipped past
    their creation quarter's end must rise from first to last quarter by
    at least min_increase_pp."""
    if "expected_close_date" not in opp.columns:
        r = _result(False, "no expected_close_date column",
                    f">= +{params['min_increase_pp']}pp",
                    "criterion requires a pipeline block in simulator.json",
                    -float(params["min_increase_pp"]))
        r["structural"] = True
        return r
    qends = resolve_quarter_ends(params)
    open_rows = _open_pipeline(opp).copy()
    if not len(open_rows):
        r = _result(False, "no open pipeline", ">=",
                    "no open rows to measure slippage on", -1.0)
        r["structural"] = True
        return r
    ec = pd.to_datetime(open_rows["expected_close_date"])
    creation_qe = pd.to_datetime(open_rows["fiscal_quarter"].map(qends))
    open_rows["slipped"] = (ec > creation_qe).astype(int)
    rates = open_rows.groupby("fiscal_quarter")["slipped"].mean() * 100
    labels = [l for l in qends if l in rates.index]
    first, last = rates.get(labels[0], 0.0), rates.get(labels[-1], 0.0)
    delta = last - first
    need = float(params["min_increase_pp"])
    detail = "; ".join(f"{k}: {rates[k]:.0f}%" for k in labels) + \
        f"; delta {delta:+.1f}pp"
    return _result(delta >= need, f"{delta:+.1f}pp slip-rate change",
                   f">= +{need:g}pp", detail, delta - need)


def check_coverage_ratio(opp, accounts, params):
    """P4 (#21): open-pipeline value closing in `quarter` divided by that
    quarter's plan target must be at least min_multiple."""
    plan = params.get("_quota_df")
    need = float(params["min_multiple"])
    if plan is None or not len(plan):
        r = _result(False, "no quota_plan sheet", f">= {need}x",
                    "criterion requires a quota block in simulator.json",
                    -need)
        r["structural"] = True
        return r
    quarter = params["quarter"]
    offset = int(params.get("target_quarter_offset", 0))
    if offset:
        labels = list(resolve_quarter_ends(params))
        qi = labels.index(quarter) + offset
        if not (0 <= qi < len(labels)):
            r = _result(False, "quarter+offset out of range", f">= {need}x",
                        "invalid target_quarter_offset", -need)
            r["structural"] = True
            return r
        quarter = labels[qi]
    prow = plan[plan["fiscal_quarter"] == quarter] \
        if "plan_unit" in plan.columns or "segment" in plan.columns else plan
    target = float(prow["target_realized_usd"].sum()) if len(prow) else 0.0
    open_rows = _open_pipeline(opp)
    if "expected_close_date" not in open_rows.columns or not len(open_rows):
        r = _result(False, "no open pipeline", f">= {need}x",
                    "criterion requires a pipeline block", -need)
        r["structural"] = True
        return r
    in_q = open_rows[pd.to_datetime(
        open_rows["expected_close_date"]).dt.strftime("%Y-%m-%d")
        <= str(resolve_quarter_ends(params).get(quarter, "9999-12-31"))]
    value = _pipeline_value(in_q)
    ratio = value / target if target else float("nan")
    detail = (f"${value:,.0f} open vs ${target:,.0f} target in "
              f"{quarter} = {ratio:.2f}x")
    return _result(ratio >= need, f"{ratio:.2f}x coverage",
                   f">= {need:g}x", detail, ratio - need)


def check_pipeline_concentration(opp, accounts, params):
    """P4 (#21): top-N ACCOUNTS' share of open-pipeline VALUE in the last
    quarter must be at least min_top_share_pct."""
    n_top = int(params.get("top_n_accounts", 5))
    needed = float(params["min_top_share_pct"])
    open_rows = _open_pipeline(opp)
    if not len(open_rows):
        r = _result(False, "no open pipeline", f">= {needed}%",
                    "criterion requires a pipeline block", -needed)
        r["structural"] = True
        return r
    by_acct = open_rows.groupby("account_id")["realized_price"].sum()
    top = by_acct.nlargest(n_top).sum()
    total = by_acct.sum()
    share = top / total * 100 if total else 0.0
    detail = (f"top {n_top} accounts hold {share:.1f}% of open pipeline "
              f"value")
    return _result(share >= needed, f"{share:.1f}% top-{n_top}",
                   f">= {needed}%", detail, share - needed)

CHECKS = {
    'win_rate_flat': check_win_rate_flat,
    'avg_discount_quarter': check_avg_discount_quarter,
    'discount_trend_monotonic': check_discount_trend_monotonic,
    'region_discount_premium': check_region_discount_premium,
    'end_of_quarter_effect': check_end_of_quarter_effect,
    'realized_vs_list': check_realized_vs_list,
    'data_sanity': check_data_sanity,
    'revenue_vs_plan': check_revenue_vs_plan,
    'cycle_length_trend': check_cycle_length_trend,
    'creation_volume_trend': check_creation_volume_trend,
    'deal_size_trend': check_deal_size_trend,
    'icp_creation_shift': check_icp_creation_shift,
    'revenue_concentration': check_revenue_concentration,
    'blended_margin_trend': check_blended_margin_trend,
    'tier_share_shift': check_tier_share_shift,
    'discount_margin_link': check_discount_margin_link,
    'avg_price_by_tier': check_avg_price_by_tier,
    'gap_concentration': check_gap_concentration,
    'stage_aging': check_stage_aging,
    'slippage_trend': check_slippage_trend,
    'coverage_ratio': check_coverage_ratio,
    'pipeline_concentration': check_pipeline_concentration,
}
