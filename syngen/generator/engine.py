"""Deterministic dataset generator: reads simulator.json, emits a multi-sheet workbook.

Ported from experiments/B_config_generator/generate.py (Experiment B, gate PASS).
Business numbers live ONLY in the config - this engine never hardcodes them.
"""
import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from syngen.config import load_simulator

ACCOUNT_SUFFIXES = [
    "Group", "Holdings", "Systems", "Industries", "Labs",
    "Partners", "Logistics", "Technologies",
]

# Engine constant (like suffixes), overridable via config. WS1-lite M4:
# every account carries a market-potential figure so plan/quota narratives
# can reason about attainment vs whitespace.
DEFAULT_POTENTIAL_RANGE_USD = (25_000, 250_000)
# M5 iter 1: ideal-customer-profile flag; neutral default (no ICP accounts)
# keeps the column present for the static sheet contract without injecting
# business meaning into unconfigured runs.
DEFAULT_ICP_SHARE = 0.0


def _weight_curve(value, n_quarters):
    """A categorical weight spec is a float (static) or a dict with
    weights_by_quarter. Returns the per-quarter list either way."""
    if isinstance(value, dict):
        return [float(w) for w in value["weights_by_quarter"]]
    return [float(value)] * n_quarters


def _curve_varies(curve):
    """True when a per-quarter weight curve actually shifts between
    quarters - static curves keep the legacy sampling path (and its RNG
    stream) untouched."""
    return len(set(curve)) > 1


def build_accounts(cfg, rng):
    spec = cfg["accounts"]
    n = spec["count"]
    quarters_n = len(cfg["time_model"]["quarter_labels"])
    region_names = list(spec["regions"])
    region_curves = [_weight_curve(v, quarters_n) for v in spec["regions"].values()]
    # static account mix uses the mean weight of any per-quarter curves
    region_p = np.array([np.mean(c) for c in region_curves])
    region_p = region_p / region_p.sum()
    segment_names = list(spec["segments"])
    segment_curves = [_weight_curve(v, quarters_n) for v in spec["segments"].values()]
    segment_p = np.array([np.mean(c) for c in segment_curves])
    segment_p = segment_p / segment_p.sum()
    industries = rng.choice(spec["industries"], size=n)
    suffixes = rng.choice(ACCOUNT_SUFFIXES, size=n)
    # separate named stream: drawing potential from the main rng would shift
    # every downstream draw and silently break reproducibility of existing
    # seeded sessions (caught live by the M2 pipeline tests)
    pot_cfg = spec.get("market_potential_usd")
    if pot_cfg:
        lo, hi = float(pot_cfg["min"]), float(pot_cfg["max"])
    else:
        lo, hi = DEFAULT_POTENTIAL_RANGE_USD
    pot_rng = np.random.default_rng([int(cfg["seed"]), 1])
    potential = np.round(pot_rng.uniform(lo, hi, size=n), 2)
    icp_share = float(spec.get("icp_share", DEFAULT_ICP_SHARE))
    icp_rng = np.random.default_rng([int(cfg["seed"]), 2])
    icp = icp_rng.random(n) < icp_share
    df = pd.DataFrame(
        {
            "account_id": [f"ACC-{i + 1:04d}" for i in range(n)],
            "account_name": [
                f"{i} {s} {j + 1:02d}"
                for j, (i, s) in enumerate(zip(industries, suffixes))
            ],
            "region": rng.choice(region_names, size=n, p=region_p),
            "segment": rng.choice(segment_names, size=n, p=segment_p),
            "industry": industries,
            "market_potential_usd": potential,
            "icp": icp,
        }
    )
    # M5 iter 2 (WS5): territory hierarchy - roll regions up into sales
    # territories; unmapped regions are territories of their own.
    terr_map = spec.get("territories")
    if terr_map:
        region_to_terr = {r: t for t, rs in terr_map.items() for r in rs}
        df["territory"] = df["region"].map(
            lambda r: region_to_terr.get(r, r))
    return df


def build_opportunities(cfg, accounts_df, rng):
    spec = cfg["opportunities"]
    dspec = spec["discount"]
    quarters = cfg["time_model"]["quarter_labels"]
    quarter_ends = cfg["time_model"]["quarter_end_dates"]
    owners = spec["owners"]
    window_days = dspec["end_of_quarter_window_days"]
    eoq_share = spec["close_clustering"]["share_in_end_of_quarter_window"]
    sigma = spec["deal_size_lognormal"]["sigma"]
    size_medians = spec["deal_size_lognormal"].get("medians_by_quarter")
    outliers = spec.get("outlier_deals")

    # M5 iter 1: per-quarter categorical mix shift - sample WHICH accounts
    # generate pipeline each quarter using that quarter's weights
    seg_curves = {s: _weight_curve(v, len(quarters))
                  for s, v in cfg["accounts"].get("segments", {}).items()}
    reg_curves = {r: _weight_curve(v, len(quarters))
                  for r, v in cfg["accounts"].get("regions", {}).items()}
    mix_shifts = (any(_curve_varies(c) for c in seg_curves.values()) or
                  any(_curve_varies(c) for c in reg_curves.values()))
    acct_segments = accounts_df["segment"].to_numpy()
    acct_regions = accounts_df["region"].to_numpy()
    acct_icp = accounts_df["icp"].to_numpy()
    # M5 iter 1 (#7): per-quarter sampling preference for ICP vs non-ICP
    # accounts - lets stories say pipeline quality shifted over time
    icp_w = cfg["accounts"].get("icp_sampling_weights_by_quarter")

    # M5 iter 2: product attribution. Each opportunity draws a catalog
    # product from that quarter's mix curve (named stream [seed, 4, qi] -
    # drawing from the main rng would shift every downstream draw and break
    # reproducibility of existing stories).
    prod_spec = cfg.get("products")
    price_mult = {}
    disc_delta = {}
    if prod_spec:
        catalog = prod_spec["catalog"]
        prod_ids = [p["id"] for p in catalog]
        prod_tier = {p["id"]: p["tier"] for p in catalog}
        prod_curves = {p["id"]: _weight_curve(p["share"], len(quarters))
                       for p in catalog}
        tier_margin = prod_spec["margin_by_tier"]
        price_mult = prod_spec.get("price_multiplier_by_tier", {})
        disc_delta = prod_spec.get("discount_delta_pp_by_tier", {})
        cogs_infl = prod_spec.get("cogs_inflation_by_quarter") or \
            [1.0] * len(quarters)

    def sample_accounts(qi, n):
        if not mix_shifts and not icp_w:
            return rng.integers(0, len(accounts_df), size=n)
        if mix_shifts:
            w = np.array([seg_curves[s][qi] * reg_curves[r][qi]
                          for s, r in zip(acct_segments, acct_regions)])
        else:
            w = np.ones(len(accounts_df))
        if icp_w:
            factors = np.where(acct_icp,
                               float(icp_w["icp"][qi]),
                               float(icp_w["non_icp"][qi]))
            w = w * factors
        total = w.sum()
        if total <= 0:
            return rng.integers(0, len(accounts_df), size=n)
        return rng.choice(len(accounts_df), size=n, p=w / total)

    rows = []
    seq = 0
    for qi, (label, q_end_str) in enumerate(zip(quarters, quarter_ends)):
        q_end = pd.Timestamp(q_end_str)
        q_start = q_end - pd.DateOffset(months=3) + pd.Timedelta(days=1)
        q_len_days = (q_end - q_start).days + 1
        multipliers = spec.get("volume_multipliers")
        n = int(round(spec["per_quarter"] *
                      (multipliers[qi] if multipliers else 1.0)))

        acct_idx = sample_accounts(qi, n)
        accts = accounts_df.iloc[acct_idx].reset_index(drop=True)

        if prod_spec and n:
            # per-quarter product mix (own named stream, see note above)
            pr_rng = np.random.default_rng([int(cfg["seed"]), 4, qi])
            mix = np.array([prod_curves[pid][qi] for pid in prod_ids])
            if mix.sum() <= 0:
                prod_pick = pr_rng.choice(len(prod_ids), size=n)
            else:
                prod_pick = pr_rng.choice(len(prod_ids), size=n,
                                          p=mix / mix.sum())
            picked_ids = [prod_ids[i] for i in prod_pick]
            picked_tiers = [prod_tier[pid] for pid in picked_ids]
            cogs_ratios = np.round(
                [(1.0 - float(tier_margin[t])) * float(cogs_infl[qi])
                 for t in picked_tiers], 4)
        else:
            picked_ids = [None] * n
            picked_tiers = [None] * n
            cogs_ratios = np.full(n, np.nan)

        win_rate_q = spec["win_rate"] + rng.uniform(
            -spec["win_rate_jitter"], spec["win_rate_jitter"]
        )
        won = rng.random(n) < win_rate_q

        early_offsets = rng.integers(0, q_len_days - window_days, size=n)
        eoq_offsets = rng.integers(q_len_days - window_days, q_len_days, size=n)
        in_eoq = rng.random(n) < eoq_share
        offsets = np.where(in_eoq, eoq_offsets, early_offsets)
        close_dates = q_start + pd.to_timedelta(offsets, unit="D")

        # durations: legacy [lo, hi] uniform, or per-quarter normal curve
        # (M4 domain B: sales-cycle slowdown)
        dur_spec = spec["deal_duration_days"]
        if isinstance(dur_spec, dict):
            mean = dur_spec["means"][qi]
            spread = dur_spec.get("spread", 10)
            durations = np.clip(np.round(rng.normal(mean, spread, size=n)),
                                1, None).astype(int)
        else:
            durations = rng.integers(dur_spec[0], dur_spec[1], size=n)
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
        # M5 iter 2 (WS4): cross-field coupling primitive - discounts may
        # shift by product tier BEFORE clipping (e.g. high-margin tiers
        # discounted harder), then realized is derived normally so the
        # identity holds.
        if disc_delta:
            delta = np.array(
                [float(disc_delta.get(t, 0.0)) for t in picked_tiers])
            discount = np.clip(base + noise + boost + delta,
                               dspec["min_pct"], dspec["max_pct"])
        else:
            discount = np.clip(base + noise + boost,
                               dspec["min_pct"], dspec["max_pct"])

        discount_pct_rounded = np.round(discount, 2)
        median_usd = size_medians[qi] if size_medians else \
            spec["deal_size_lognormal"]["median_usd"]
        list_price = np.round(rng.lognormal(np.log(median_usd), sigma, size=n), 2)
        if price_mult:
            mult_arr = np.array(
                [float(price_mult.get(t, 1.0)) for t in picked_tiers])
            list_price = np.round(list_price * mult_arr, 2)
        realized_price = np.round(
            list_price * (1.0 - discount_pct_rounded / 100.0), 2
        )

        # M5 iter 1: whale/mixture deals (#25). Scale list_price then
        # RECOMPUTE realized from it - scaling both independently and
        # rounding would break the derived-field identity by up to
        # multiplier * $0.005 (caught by test).
        if outliers and n:
            k = max(1, int(round(n * float(outliers["share"]))))
            wh_rng = np.random.default_rng([int(cfg["seed"]), 3, qi])
            whale_local = wh_rng.choice(n, size=k, replace=False)
            mult = float(outliers["multiplier"])
            keep_whale = 1 - discount_pct_rounded[whale_local] / 100
            list_price[whale_local] = np.round(
                list_price[whale_local] * mult, 2)
            realized_price[whale_local] = np.round(
                list_price[whale_local] * keep_whale, 2)

        for j in range(n):
            seq += 1
            row = {
                "opportunity_id": f"OPP-{seq:05d}",
                "account_id": accts.loc[j, "account_id"],
                "owner": str(rng.choice(owners)),
                "region": accts.loc[j, "region"],
                "segment": accts.loc[j, "segment"],
                "icp": bool(accts.loc[j, "icp"]),
                "fiscal_quarter": label,
                "created_date": created_dates[j].date(),
                "close_date": close_dates[j].date(),
                "stage": "Closed Won" if won[j] else "Closed Lost",
                "list_price": list_price[j],
                "discount_pct": float(discount_pct_rounded[j]),
                "realized_price": realized_price[j],
            }
            if "territory" in accts.columns:
                row["territory"] = accts.loc[j, "territory"]
            if prod_spec:
                row["product_id"] = picked_ids[j]
                row["product_tier"] = picked_tiers[j]
                row["cogs_ratio"] = float(cogs_ratios[j])
            rows.append(row)

    return pd.DataFrame(rows)


def _quota_dimension(cfg):
    """Quota plan units: 'segment' (legacy default) or 'territory'."""
    quota = cfg.get("quota") or {}
    if quota.get("by_territory"):
        return "territory", quota["by_territory"]
    return "segment", quota.get("by_segment")


def build_quota_plan(cfg):
    """quota_plan sheet from the optional config quota block (WS3).

    Unified schema across plan dimensions: plan_unit_type names the
    grouping column ('segment' or 'territory'), plan_unit carries its
    value. Keeps downstream checks domain-neutral.
    """
    dim, targets = _quota_dimension(cfg)
    if not targets:
        return None
    quarters = cfg["time_model"]["quarter_labels"]
    rows = [
        {"plan_unit_type": dim, "plan_unit": unit, "fiscal_quarter": label,
         "target_realized_usd": float(t)}
        for unit, curve in targets.items()
        for label, t in zip(quarters, curve)
    ]
    return pd.DataFrame(rows)


def apply_raking(opp_df, cfg):
    """Deterministic monetary raking pass (WS3 aggregate targets).

    Per plan-unit x quarter stratum: scale list_price so closed-won
    realized revenue hits the quota target TIMES the unit's configured
    attainment ratio (default 1.0). This is what lets a story say
    "Enterprise missed plan by 5%" - the plan stays the plan, and actuals
    land at 95% of it. realized is recomputed from the scaled list,
    preserving the derived-field identity exactly.

    All rows in a stratum scale together (won and lost), keeping the
    stratum's price distribution coherent. Margin fields survive: the
    cogs_ratio column is per-deal and unscaled, so margin_pct is invariant
    under uniform price scaling.
    """
    if not cfg.get("quota"):
        return opp_df
    quarters = cfg["time_model"]["quarter_labels"]
    dim, targets = _quota_dimension(cfg)
    attainment = cfg["quota"].get("attainment") or \
        cfg["quota"].get("attainment_by_segment", {})
    df = opp_df.copy()
    for unit, curve in targets.items():
        raw_ratio = attainment.get(unit, 1.0)
        try:
            ratio = float(raw_ratio)
        except (TypeError, ValueError):
            ratio = 1.0  # defense in depth: never crash raking on a bad type
        for qi, label in enumerate(quarters):
            target = float(curve[qi]) * ratio
            mask = (df[dim] == unit) & (df["fiscal_quarter"] == label)
            won_mask = mask & (df["stage"] == "Closed Won")
            won_sum = df.loc[won_mask, "realized_price"].sum()
            if target <= 0 or won_sum <= 0:
                continue  # cannot rake an empty or unsellable stratum
            k = target / won_sum
            keep = 1 - df.loc[mask, "discount_pct"] / 100
            df.loc[mask, "list_price"] = (df.loc[mask, "list_price"] * k).round(2)
            # recompute from the scaled list so realized == list*(1-d) exactly
            df.loc[mask, "realized_price"] = (
                df.loc[mask, "list_price"] * keep
            ).round(2)
            # absorb rounding drift into the largest won deal so attainment
            # is exact to the cent while keeping the identity intact
            residual = round(target - df.loc[won_mask, "realized_price"].sum(), 2)
            if residual:
                idx = df.loc[won_mask, "realized_price"].idxmax()
                kf = 1 - df.at[idx, "discount_pct"] / 100
                df.loc[idx, "list_price"] = round(
                    df.loc[idx, "list_price"] + residual / kf, 2)
                df.loc[idx, "realized_price"] = round(
                    df.loc[idx, "list_price"] * kf, 2)
    return df


def build_summary(opp_df, quarters):
    """Derived view over fact rows ONLY - never authored independently."""
    summary_columns = ["fiscal_quarter", "opportunities", "closed_won",
                       "win_rate_pct", "avg_discount_won_pct",
                       "realized_vs_list_pct", "total_realized_usd"]
    if opp_df.empty:
        # e.g. per_quarter=0: keep the sheet contract, rows are empty
        return pd.DataFrame(columns=summary_columns)
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
    quota_df = build_quota_plan(cfg)
    if quota_df is not None:
        opp_df = apply_raking(opp_df, cfg)
    summary_df = build_summary(opp_df, cfg["time_model"]["quarter_labels"])
    frames = {
        "accounts": accounts_df,
        "opportunities": opp_df,
        "quarterly_summary": summary_df,
    }
    if quota_df is not None:
        frames["quota_plan"] = quota_df
    return frames


def _meta_frame(cfg):
    """_synngen_meta sheet per contracts section 5 (repro info for humans)."""
    payload = json.dumps(cfg, sort_keys=True).encode("utf-8")
    return pd.DataFrame([{
        "seed": cfg["seed"],
        "config_hash": hashlib.sha256(payload).hexdigest()[:12],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }])


def write_workbook(frames, workbook_path, meta=None):
    out_path = Path(workbook_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet_order = ["accounts", "opportunities", "quarterly_summary",
                   "quota_plan", "_synngen_meta"]
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for name in sheet_order:
            if name in frames:
                frames[name].to_excel(writer, sheet_name=name, index=False)
        if meta is not None and "_synngen_meta" not in frames:
            meta.to_excel(writer, sheet_name="_synngen_meta", index=False)
    return out_path


def generate_to_workbook(cfg_or_path):
    """Convenience: generate and write in one call. Returns (frames, path)."""
    cfg = load_simulator(cfg_or_path) if isinstance(cfg_or_path, (str, Path)) else cfg_or_path
    frames = generate(cfg)
    path = write_workbook(frames, cfg["output"]["workbook"],
                          meta=_meta_frame(cfg))
    return frames, path
