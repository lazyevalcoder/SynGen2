"""Deterministic dataset generator: reads simulator.json, emits a multi-sheet workbook.

Ported from experiments/B_config_generator/generate.py (Experiment B, gate PASS).
Business numbers live ONLY in the config - this engine never hardcodes them.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from syngen.config import load_simulator

ACCOUNT_SUFFIXES = [
    "Group", "Holdings", "Systems", "Industries", "Labs",
    "Partners", "Logistics", "Technologies",
]


def build_accounts(cfg, rng):
    spec = cfg["accounts"]
    n = spec["count"]
    region_names = list(spec["regions"])
    region_p = list(spec["regions"].values())
    segment_names = list(spec["segments"])
    segment_p = list(spec["segments"].values())
    industries = rng.choice(spec["industries"], size=n)
    suffixes = rng.choice(ACCOUNT_SUFFIXES, size=n)
    return pd.DataFrame(
        {
            "account_id": [f"ACC-{i + 1:04d}" for i in range(n)],
            "account_name": [
                f"{i} {s} {j + 1:02d}"
                for j, (i, s) in enumerate(zip(industries, suffixes))
            ],
            "region": rng.choice(region_names, size=n, p=region_p),
            "segment": rng.choice(segment_names, size=n, p=segment_p),
            "industry": industries,
        }
    )


def build_opportunities(cfg, accounts_df, rng):
    spec = cfg["opportunities"]
    dspec = spec["discount"]
    quarters = cfg["time_model"]["quarter_labels"]
    quarter_ends = cfg["time_model"]["quarter_end_dates"]
    owners = spec["owners"]
    window_days = dspec["end_of_quarter_window_days"]
    eoq_share = spec["close_clustering"]["share_in_end_of_quarter_window"]
    dur_lo, dur_hi = spec["deal_duration_days"]
    median_usd = spec["deal_size_lognormal"]["median_usd"]
    sigma = spec["deal_size_lognormal"]["sigma"]

    rows = []
    seq = 0
    for qi, (label, q_end_str) in enumerate(zip(quarters, quarter_ends)):
        q_end = pd.Timestamp(q_end_str)
        q_start = q_end - pd.DateOffset(months=3) + pd.Timedelta(days=1)
        q_len_days = (q_end - q_start).days + 1
        n = spec["per_quarter"]

        acct_idx = rng.integers(0, len(accounts_df), size=n)
        accts = accounts_df.iloc[acct_idx].reset_index(drop=True)

        win_rate_q = spec["win_rate"] + rng.uniform(
            -spec["win_rate_jitter"], spec["win_rate_jitter"]
        )
        won = rng.random(n) < win_rate_q

        early_offsets = rng.integers(0, q_len_days - window_days, size=n)
        eoq_offsets = rng.integers(q_len_days - window_days, q_len_days, size=n)
        in_eoq = rng.random(n) < eoq_share
        offsets = np.where(in_eoq, eoq_offsets, early_offsets)
        close_dates = q_start + pd.to_timedelta(offsets, unit="D")

        durations = rng.integers(dur_lo, dur_hi, size=n)
        created_dates = close_dates - pd.to_timedelta(durations, unit="D")

        base = np.array(
            [dspec["base_by_quarter"][r][qi] for r in accts["region"]], dtype=float
        )
        noise = rng.normal(0.0, dspec["noise_sd_pp"], size=n)
        boost = np.where(
            close_dates >= q_end - pd.Timedelta(days=window_days - 1),
            dspec["end_of_quarter_boost_pp"],
            0.0,
        )
        discount = np.clip(base + noise + boost, dspec["min_pct"], dspec["max_pct"])

        discount_pct_rounded = np.round(discount, 2)
        list_price = np.round(rng.lognormal(np.log(median_usd), sigma, size=n), 2)
        realized_price = np.round(
            list_price * (1.0 - discount_pct_rounded / 100.0), 2
        )

        for j in range(n):
            seq += 1
            rows.append(
                {
                    "opportunity_id": f"OPP-{seq:05d}",
                    "account_id": accts.loc[j, "account_id"],
                    "owner": str(rng.choice(owners)),
                    "region": accts.loc[j, "region"],
                    "segment": accts.loc[j, "segment"],
                    "fiscal_quarter": label,
                    "created_date": created_dates[j].date(),
                    "close_date": close_dates[j].date(),
                    "stage": "Closed Won" if won[j] else "Closed Lost",
                    "list_price": list_price[j],
                    "discount_pct": float(discount_pct_rounded[j]),
                    "realized_price": realized_price[j],
                }
            )

    return pd.DataFrame(rows)


def build_summary(opp_df, quarters):
    won = opp_df[opp_df["stage"] == "Closed Won"]
    records = []
    for label in quarters:
        q_all = opp_df[opp_df["fiscal_quarter"] == label]
        q_won = won[won["fiscal_quarter"] == label]
        total = len(q_all)
        wins = len(q_won)
        records.append(
            {
                "fiscal_quarter": label,
                "opportunities": total,
                "closed_won": wins,
                "win_rate_pct": round(wins / total * 100, 2) if total else 0.0,
                "avg_discount_won_pct": round(q_won["discount_pct"].mean(), 2) if wins else 0.0,
                "realized_vs_list_pct": round(
                    q_won["realized_price"].sum() / q_won["list_price"].sum() * 100, 2
                ) if wins else 0.0,
                "total_realized_usd": round(q_won["realized_price"].sum(), 2),
            }
        )
    return pd.DataFrame(records)


def generate(cfg_or_path):
    """Generate all dataframes from a simulator config (path or dict). Returns dict of frames."""
    cfg = load_simulator(cfg_or_path) if isinstance(cfg_or_path, (str, Path)) else cfg_or_path
    rng = np.random.default_rng(cfg["seed"])
    accounts_df = build_accounts(cfg, rng)
    opp_df = build_opportunities(cfg, accounts_df, rng)
    summary_df = build_summary(opp_df, cfg["time_model"]["quarter_labels"])
    return {
        "accounts": accounts_df,
        "opportunities": opp_df,
        "quarterly_summary": summary_df,
    }


def write_workbook(frames, workbook_path):
    out_path = Path(workbook_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        frames["accounts"].to_excel(writer, sheet_name="accounts", index=False)
        frames["opportunities"].to_excel(writer, sheet_name="opportunities", index=False)
        frames["quarterly_summary"].to_excel(writer, sheet_name="quarterly_summary", index=False)
    return out_path


def generate_to_workbook(cfg_or_path):
    """Convenience: generate and write in one call. Returns (frames, path)."""
    cfg = load_simulator(cfg_or_path) if isinstance(cfg_or_path, (str, Path)) else cfg_or_path
    frames = generate(cfg)
    path = write_workbook(frames, cfg["output"]["workbook"])
    return frames, path
