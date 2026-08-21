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
    for label in QUARTER_ENDS:
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
            for q in QUARTER_ENDS]
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
    for label, end_str in QUARTER_ENDS.items():
        q_end = pd.Timestamp(end_str)
        q_start = quarter_start(end_str)
        q_won = won_deals(opp)
        q_won = q_won[q_won["fiscal_quarter"] == label]
        day = (q_won["close_date"] - q_start).dt.days + 1
        q_len = (q_end - q_start).days + 1
        eoq_disc.append(q_won[day > q_len - window]["discount_pct"])
        mid_disc.append(q_won[(day >= 15) & (day <= 74)]["discount_pct"])
    eoq_mean = pd.concat(eoq_disc).mean()
    mid_mean = pd.concat(mid_disc).mean()
    gap = eoq_mean - mid_mean
    needed = params["min_gap_pp"]
    detail = (
        f"EOQ avg={eoq_mean:.2f}% (n={sum(len(s) for s in eoq_disc)}), "
        f"mid-quarter avg={mid_mean:.2f}% (n={sum(len(s) for s in mid_disc)})"
    )
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
    for label, end_str in QUARTER_ENDS.items():
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


CHECKS = {
    "win_rate_flat": check_win_rate_flat,
    "avg_discount_quarter": check_avg_discount_quarter,
    "discount_trend_monotonic": check_discount_trend_monotonic,
    "region_discount_premium": check_region_discount_premium,
    "end_of_quarter_effect": check_end_of_quarter_effect,
    "realized_vs_list": check_realized_vs_list,
    "data_sanity": check_data_sanity,
}
