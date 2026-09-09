import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

QUARTER_ENDS = {
    "FY26-Q1": "2026-03-31",
    "FY26-Q2": "2026-06-30",
    "FY26-Q3": "2026-09-30",
    "FY26-Q4": "2026-12-31",
}


def load_workbook(path):
    path = Path(path)
    opp = pd.read_excel(path, sheet_name="opportunities")
    accounts = pd.read_excel(path, sheet_name="accounts")
    opp["close_date"] = pd.to_datetime(opp["close_date"])
    return opp, accounts


def won_deals(opp):
    return opp[opp["stage"] == "Closed Won"]


def quarter_of(date_str):
    q_start = pd.Timestamp(date_str) - pd.DateOffset(months=3) + pd.Timedelta(days=1)
    return q_start


def check_win_rate_flat(opp, params):
    rates = {}
    for label in QUARTER_ENDS:
        q = opp[opp["fiscal_quarter"] == label]
        closed = q[q["stage"].isin(["Closed Won", "Closed Lost"])]
        rates[label] = len(closed[closed["stage"] == "Closed Won"]) / len(closed) * 100 if len(closed) else 0.0
    mean = np.mean(list(rates.values()))
    worst = max(abs(r - mean) for r in rates.values())
    ok = worst <= params["band_pp"]
    detail = f"quarters={{{', '.join(f'{k}: {v:.1f}' for k, v in rates.items())}}}, mean={mean:.1f}, max dev={worst:.2f}pp"
    return ok, f"{worst:.2f}pp max deviation", f"<= {params['band_pp']}pp of mean", detail


def check_avg_discount_quarter(opp, params):
    won_q = won_deals(opp)
    won_q = won_q[won_q["fiscal_quarter"] == params["quarter"]]
    actual = won_q["discount_pct"].mean()
    target = params["target_pct"]
    tol = params["tolerance_pp"]
    ok = abs(actual - target) <= tol
    detail = f"{params['quarter']} avg discount on {len(won_q)} won deals"
    return ok, f"{actual:.2f}%", f"{target}% +/-{tol}pp", detail


def check_discount_trend_monotonic(opp, params):
    won_q = won_deals(opp)
    avgs = [won_q[won_q["fiscal_quarter"] == q]["discount_pct"].mean() for q in QUARTER_ENDS]
    dips = [avgs[i - 1] - avgs[i] for i in range(1, len(avgs))]
    worst_dip = max(dips)
    ok = worst_dip <= params["max_dip_pp"]
    trend = " -> ".join(f"{a:.1f}" for a in avgs)
    detail = f"quarterly avgs: {trend}"
    return ok, f"{worst_dip:.2f}pp worst dip", f"<= {params['max_dip_pp']}pp", detail


def check_region_discount_premium(opp, params):
    won_q = won_deals(opp)
    h2 = won_q[won_q["fiscal_quarter"].isin(params["quarters"])]
    region_avgs = h2.groupby("region")["discount_pct"].mean()
    prem = params["region"]
    gaps = {other: region_avgs[prem] - region_avgs[other] for other in params["vs"]}
    worst_gap = min(gaps.values())
    ok = worst_gap >= params["min_premium_pp"]
    gap_str = ", ".join(f"vs {k}: {v:+.2f}pp" for k, v in gaps.items())
    detail = f"H2 avgs: {{{', '.join(f'{r}: {v:.1f}' for r, v in region_avgs.items())}}}; {gap_str}"
    return ok, f"{worst_gap:+.2f}pp worst gap", f">= +{params['min_premium_pp']}pp", detail


def check_end_of_quarter_effect(opp, params):
    window = params["window_days"]
    eoq_disc, mid_disc = [], []
    for label, end_str in QUARTER_ENDS.items():
        q_end = pd.Timestamp(end_str)
        q_start = quarter_of(end_str)
        q_won = won_deals(opp)
        q_won = q_won[q_won["fiscal_quarter"] == label]
        day = (q_won["close_date"] - q_start).dt.days + 1
        q_len = (q_end - q_start).days + 1
        eoq_disc.append(q_won[day > q_len - window]["discount_pct"])
        mid_lo, mid_hi = 15, 74
        mid_disc.append(q_won[(day >= mid_lo) & (day <= mid_hi)]["discount_pct"])
    eoq_mean = pd.concat(eoq_disc).mean()
    mid_mean = pd.concat(mid_disc).mean()
    gap = eoq_mean - mid_mean
    ok = gap >= params["min_gap_pp"]
    detail = f"EOQ avg={eoq_mean:.2f}% (n={sum(len(s) for s in eoq_disc)}), mid-quarter avg={mid_mean:.2f}% (n={sum(len(s) for s in mid_disc)})"
    return ok, f"{gap:+.2f}pp gap", f">= +{params['min_gap_pp']}pp", detail


def check_realized_vs_list(opp, params):
    won_q = won_deals(opp)

    def pct_for(label):
        d = won_q[won_q["fiscal_quarter"] == label]
        return d["realized_price"].sum() / d["list_price"].sum() * 100

    start_actual = pct_for(params["quarter_start"])
    end_actual = pct_for(params["quarter_end"])
    tol = params["tolerance_pp"]
    ok_start = abs(start_actual - params["target_start_pct"]) <= tol
    ok_end = abs(end_actual - params["target_end_pct"]) <= tol
    ok = ok_start and ok_end
    detail = (
        f"{params['quarter_start']}: {start_actual:.2f}% (target {params['target_start_pct']}%), "
        f"{params['quarter_end']}: {end_actual:.2f}% (target {params['target_end_pct']}%)"
    )
    return ok, f"{start_actual:.1f}% -> {end_actual:.1f}%", f"{params['target_start_pct']}% -> {params['target_end_pct']}% +/-{tol}pp", detail


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
    out_of_quarter = []
    for label, end_str in QUARTER_ENDS.items():
        q_end = pd.Timestamp(end_str)
        q_start = quarter_of(end_str)
        m = opp["fiscal_quarter"] == label
        bad = m & ((opp["close_date"] < q_start) | (opp["close_date"] > q_end))
        out_of_quarter.append(int(bad.sum()))
    if sum(out_of_quarter):
        problems.append(f"{sum(out_of_quarter)} close dates outside their quarter")
    ok = not problems
    detail = "; ".join(problems) if problems else "all constraints satisfied"
    return ok, "clean" if ok else "violations", "no violations", detail


CHECKS = {
    "win_rate_flat": lambda opp, acc, p: check_win_rate_flat(opp, p),
    "avg_discount_quarter": lambda opp, acc, p: check_avg_discount_quarter(opp, p),
    "discount_trend_monotonic": lambda opp, acc, p: check_discount_trend_monotonic(opp, p),
    "region_discount_premium": lambda opp, acc, p: check_region_discount_premium(opp, p),
    "end_of_quarter_effect": lambda opp, acc, p: check_end_of_quarter_effect(opp, p),
    "realized_vs_list": lambda opp, acc, p: check_realized_vs_list(opp, p),
    "data_sanity": lambda opp, acc, p: check_data_sanity(opp, acc, p),
}


def run_validation(workbook_path, criteria_path):
    opp, accounts = load_workbook(workbook_path)
    with open(criteria_path, encoding="utf-8") as f:
        criteria = json.load(f)["criteria"]

    results = []
    for c in criteria:
        fn = CHECKS[c["check"]]
        try:
            ok, actual, target, detail = fn(opp, accounts, c["params"])
            results.append({"id": c["id"], "name": c["name"], "actual": actual,
                            "target": target, "verdict": "PASS" if ok else "FAIL", "detail": detail})
        except Exception as e:
            results.append({"id": c["id"], "name": c["name"], "actual": "ERROR",
                            "target": "-", "verdict": "ERROR", "detail": str(e)})
    return results


def print_results(results):
    print(f"{'ID':<5} {'Verdict':<8} {'Actual':<22} {'Target':<28} Criterion")
    print("-" * 110)
    for r in results:
        print(f"{r['id']:<5} {r['verdict']:<8} {r['actual']:<22} {r['target']:<28} {r['name']}")
        if r["verdict"] != "PASS":
            print(f"{'':5} -> {r['detail']}")
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    total = len(results)
    print("-" * 110)
    verdict = "STORY LANDED" if passed == total else "STORY NOT LANDED"
    print(f"{passed}/{total} criteria passed - {verdict}")
    return passed == total


def main():
    workbook = sys.argv[1] if len(sys.argv) > 1 else "../B_config_generator/output/syngen_demo.xlsx"
    criteria = sys.argv[2] if len(sys.argv) > 2 else "criteria.json"
    print(f"Validating: {workbook}\n")
    results = run_validation(workbook, criteria)
    all_pass = print_results(results)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
