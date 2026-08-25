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
# WS7 (M5 iter 4): canonical motion labels - an account's first won deal
# in the window is New Logo, every later one Expansion.
NEW_LOGO = "New Logo"
EXPANSION = "Expansion"
CLOSED_STAGES_ENGINE = {"Closed Won", "Closed Lost"}


# M5 iter 4 (WS1 rest): rep-name pools for the canonical Rep roster.
# Deterministic picks from the named stream [seed, 8] - same discipline as
# account potentials and product mixes.
REP_FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Casey", "Riley",
    "Morgan", "Avery", "Quinn", "Dana", "Jamie",
]
REP_LAST_NAMES = [
    "Nguyen", "Patel", "Garcia", "Kim", "Okafor",
    "Silva", "Haddad", "Novak", "Iyer", "Brooks",
]


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
    # M5 iter 3 fix (live s18): a region MAY be split across several
    # territories (e.g., AMER -> East/West). Split that region's accounts
    # evenly using the named stream [seed, 6] - last-one-wins dict mapping
    # silently starved half the plan units of any pipeline.
    terr_map = spec.get("territories")
    if terr_map:
        region_groups = {}
        for tname, members in terr_map.items():
            for r in members:
                region_groups.setdefault(r, []).append(tname)
        split_rng = np.random.default_rng([int(cfg["seed"]), 6])
        n_acc = len(df)

        def pick_terr(region):
            group = region_groups.get(region, [region])
            if len(group) == 1:
                return group[0]
            return group[int(split_rng.integers(0, len(group)))]

        df["territory"] = [pick_terr(r) for r in df["region"]]
    # M5 iter 4 (F28, landing s4): optional per-territory / per-region
    # potential overrides. The global uniform draw is remapped affinely so
    # whitespace stories can concentrate market potential where pipeline
    # sampling doesn't reach - the two are otherwise proportionally locked
    # (both follow region weights), leaving potential_coverage_gap with no
    # expressible signal. Same stream, same ranks, deterministic.
    pot_overrides = {}
    if pot_cfg:
        pot_overrides = pot_cfg.get("by_territory") or \
            pot_cfg.get("by_region") or {}
    if pot_overrides:
        key_col = "territory" if "territory" in df.columns else "region"
        keys = df[key_col].to_numpy()
        for i in range(n):
            r_spec = pot_overrides.get(keys[i])
            if not r_spec:
                continue
            u = (potential[i] - lo) / (hi - lo)
            rlo, rhi = float(r_spec["min"]), float(r_spec["max"])
            potential[i] = round(rlo + u * (rhi - rlo), 2)
        df["market_potential_usd"] = potential
    return df


def build_ownership(cfg, accounts_df):
    """WS7 temporal entity (M5 iter 4): dated rep-account ownership.

    One row per account x fiscal quarter: who owned it that quarter
    (owner NaN = unowned - consolidation stories leave strategic accounts
    without one). Deterministic via named stream [seed, 9]:

      - Q1: uniform draw from the owner pool, then unowned_share[0]
            of accounts dropped to unowned
      - Q>1: churn_share[qi] of owned accounts reassigned to a DIFFERENT
            owner; then unowned_share[qi] set unowned

    Returns (ownership_df, changed_map) where changed_map[qi] is the set
    of account_ids whose owner changed vs the previous quarter (used for
    the optional post-change win-rate coupling in #9-style stories).
    """
    spec = cfg.get("ownership")
    if not spec:
        return None, None
    labels = cfg["time_model"]["quarter_labels"]
    pool = list(spec.get("owner_pool") or cfg["opportunities"]["owners"])
    unowned_curve = spec.get("unowned_share_by_quarter") or [0.0] * len(labels)
    churn_curve = spec.get("churn_share_by_quarter") or [0.0] * len(labels)
    rng = np.random.default_rng([int(cfg["seed"]), 9])
    ids = accounts_df["account_id"].to_numpy()
    # object dtype so unowned stays real None (a str array would store
    # the literal string "None" and every downstream isna() would lie)
    owners = np.array([str(rng.choice(pool)) for _ in ids], dtype=object)

    def drop_unowned(cur_owners, share):
        k = int(round(len(ids) * float(share)))
        if k <= 0:
            return cur_owners, np.array([], dtype=int)
        pick = rng.choice(len(ids), size=k, replace=False)
        cur = cur_owners.copy()
        cur[pick] = None
        return cur, pick

    owners, _ = drop_unowned(owners, unowned_curve[0])
    rows = [(ids[i], labels[0], owners[i]) for i in range(len(ids))]
    changed_by_q = {}
    for qi in range(1, len(labels)):
        changed = set()
        k = int(round(len(ids) * float(churn_curve[qi])))
        if k > 0:
            pick = rng.choice(len(ids), size=k, replace=False)
            for i in pick:
                old = owners[i]
                if old is not None and len(pool) > 1:
                    new = str(rng.choice([p for p in pool if p != old]))
                elif old is None:
                    new = str(rng.choice(pool))
                else:
                    new = old  # single-owner pool: cannot reassign
                if new != old:
                    owners[i] = new
                    changed.add(str(ids[i]))
        owners, _ = drop_unowned(owners, unowned_curve[qi])
        rows += [(ids[i], labels[qi], owners[i]) for i in range(len(ids))]
        changed_by_q[labels[qi]] = changed
    df = pd.DataFrame(rows, columns=["account_id", "fiscal_quarter", "owner"])
    return df, changed_by_q


def build_opportunities(cfg, accounts_df, rng, ownership=None):
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

    # M5 iter 3 (P4): open-pipeline state machine. A per-quarter share of
    # created opportunities stays OPEN in a lifecycle stage instead of
    # closing; open rows carry expected_close_date (possibly slipped past
    # the quarter) and feed the stage-history entity. All pipeline draws
    # use the named stream [seed, 5, qi] - main-rng order is untouched, so
    # stories without a pipeline block reproduce byte-identically.
    rows = []
    seq = 0
    stage_history = []  # canonical Opportunity Stage History entity (P4)
    ownership_cfg = cfg.get("ownership") or {}
    pipe_spec = cfg.get("pipeline")
    if pipe_spec:
        p_open = pipe_spec["share_open_by_quarter"]
        stage_names = list(pipe_spec["stage_names"])
        stage_w = pipe_spec.get("stage_weights")
        if stage_w:
            wsum = sum(float(w) for w in stage_w)
            stage_p = [float(w) / wsum for w in stage_w]
        else:
            stage_p = None
        slip_rates = pipe_spec.get("slippage_rate_by_quarter")

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
        # WS7 (#9 coupling): accounts whose owner changed THIS quarter may
        # convert worse for a while - same rng draw, shifted threshold, so
        # streams stay aligned with and without the block.
        wr_mult = 1.0
        changed_now = None
        if ownership is not None:
            wr_mult = float(ownership_cfg.get(
                "win_rate_multiplier_after_change", 1.0))
            changed_now = ownership[1].get(label, set())
        # WS8/#16 coupling: a price change bites harder where market
        # potential is low - high-potential territories hold conversion.
        price_resp = cfg.get("pricing_response")
        if price_resp:
            d_p = float(price_resp["price_change_pct_by_quarter"][qi])
            elas = float(price_resp["elasticity"])
            mit = float(price_resp.get("potential_mitigation", 0.0))
            pot = accts["market_potential_usd"].to_numpy(dtype=float)
            lo, hi = pot.min(), pot.max()
            normed = (pot - lo) / (hi - lo) if hi > lo else \
                np.full(n, 0.5)
            mults = 1.0 + (elas * d_p / 100.0) * \
                (1.0 - mit * normed)
            won = rng.random(n) < np.clip(win_rate_q * mults, 0.0, 1.0)
        elif wr_mult != 1.0 and changed_now:
            mults = np.where(
                accts["account_id"].isin(changed_now), wr_mult, 1.0)
            won = rng.random(n) < np.clip(win_rate_q * mults, 0.0, 1.0)
        else:
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
            _share_q = outliers.get("share_by_quarter") or \
                [outliers.get("share")] * len(quarters)
            k = max(1, int(round(n * float(_share_q[qi]))))
            wh_rng = np.random.default_rng([int(cfg["seed"]), 3, qi])
            whale_local = wh_rng.choice(n, size=k, replace=False)
            mult = float(outliers["multiplier"])
            keep_whale = 1 - discount_pct_rounded[whale_local] / 100
            list_price[whale_local] = np.round(
                list_price[whale_local] * mult, 2)
            realized_price[whale_local] = np.round(
                list_price[whale_local] * keep_whale, 2)

        # P4: pick this quarter's open-pipeline cohort (named stream)
        if pipe_spec and n:
            pl_rng = np.random.default_rng([int(cfg["seed"]), 5, qi])
            k_open = int(round(n * float(p_open[qi])))
            k_open = min(k_open, n)
            open_local = set(pl_rng.choice(n, size=k_open, replace=False)
                             .tolist()) if k_open else set()
            open_stage = {}
            for j in open_local:
                st = str(pl_rng.choice(stage_names, p=stage_p)) \
                    if stage_p else str(pl_rng.choice(stage_names))
                open_stage[j] = st
            slipped = set()
            if slip_rates and k_open:
                thresh = float(slip_rates[qi])
                slipped = {j for j in open_local
                           if pl_rng.random() < thresh}
        else:
            open_local = set()

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
            if pipe_spec:
                # keep expected_close_date adjacent to close_date in the
                # column contract (insertion order defines sheet columns)
                _items = list(row.items())
                _idx = [k for k, _ in _items].index("close_date") + 1
                _items.insert(_idx, ("expected_close_date", None))
                row = dict(_items)
            if j in open_local:
                # lifecycle state: still open at evaluation time. Expected
                # close is the original duration-based date; slippage pushes
                # it beyond the creation quarter's end.
                row["stage"] = open_stage[j]
                row["close_date"] = None
                expected = pd.Timestamp(close_dates[j])
                if j in slipped:
                    expected = q_end + pd.Timedelta(
                        days=int(pl_rng.integers(5, 80)))
                row["expected_close_date"] = expected.date()
                stage_history.append({
                    "opportunity_id": row["opportunity_id"],
                    "stage": open_stage[j],
                    "entered_date": created_dates[j].date(),
                    "fiscal_quarter": label,
                })
            rows.append(row)
    df = pd.DataFrame(rows)
    df.attrs["stage_history"] = pd.DataFrame(stage_history) \
        if stage_history else None
    return df


def _quota_dimension(cfg):
    """Quota plan units: 'segment' (legacy default), 'territory', or
    'motion' (New Logo / Expansion, WS7 #22)."""
    quota = cfg.get("quota") or {}
    if quota.get("by_territory"):
        return "territory", quota["by_territory"]
    if quota.get("by_motion"):
        return "motion", quota["by_motion"]
    return "segment", quota.get("by_segment")


def _capacity_dimension(cfg):
    """Capacity plan units: 'territory' or 'region'."""
    cap = cfg.get("capacity") or {}
    if cap.get("by_territory"):
        return "territory", cap["by_territory"]
    return "region", cap.get("by_region")


def build_activity(cfg, accounts_df):
    """WS7 (#13): account-activity fact table. Per account x quarter a
    touch count ~ Poisson(mean_touches[qi] * tilt_factor), where
    potential_tilt biases activity toward LOW-potential accounts
    (negative tilt) or high (positive). Named stream [seed, 10]."""
    spec = cfg.get("activity")
    if not spec:
        return None
    labels = cfg["time_model"]["quarter_labels"]
    means = spec["mean_touches_per_account_by_quarter"]
    tilt = float(spec.get("potential_tilt", 0.0))
    rng = np.random.default_rng([int(cfg["seed"]), 10])
    pot = accounts_df["market_potential_usd"].to_numpy(dtype=float)
    lo, hi = pot.min(), pot.max()
    normed = (pot - lo) / (hi - lo) if hi > lo else \
        np.full(len(pot), 0.5)
    factor = np.exp(tilt * (normed - 0.5) * 2.0) if tilt != 0.0 else \
        np.ones(len(pot))
    touches = rng.poisson(np.array(means)[np.newaxis, :] * factor[:, np.newaxis])
    ids = accounts_df["account_id"].to_numpy()
    rows = [
        (ids[i], labels[qi], int(touches[i, qi]))
        for i in range(len(ids)) for qi in range(len(labels))
    ]
    return pd.DataFrame(rows, columns=["account_id", "fiscal_quarter",
                                       "touches"])


def _apply_commit_flags(opp_df, cfg, activity_df):
    """WS7 (#14/#2): flag a share of each quarter's WON deals as the
    sales org's commit. With low_activity_bias > 0, selection is biased
    toward zero-touch accounts (the 'commit concentrated where nothing is
    happening' pathology). Named stream [seed, 11]."""
    spec = cfg["forecast"]
    labels = cfg["time_model"]["quarter_labels"]
    shares = spec.get("commit_share_of_won_by_quarter") or [1.0] * len(labels)
    bias = float(spec.get("low_activity_bias", 0.0))
    rng = np.random.default_rng([int(cfg["seed"]), 11])
    touch_key = None
    if activity_df is not None and bias != 0.0:
        touch_key = activity_df.set_index(
            ["account_id", "fiscal_quarter"])["touches"]
    opp_df["in_commit"] = False
    for qi, label in enumerate(labels):
        share = float(shares[qi])
        if share <= 0:
            continue
        m = (opp_df["fiscal_quarter"] == label) & \
            (opp_df["stage"] == "Closed Won")
        idx = opp_df.index[m].to_numpy()
        if not len(idx):
            continue
        k = max(1, int(round(len(idx) * min(share, 1.0))))
        if touch_key is not None:
            pairs = list(zip(opp_df.loc[idx, "account_id"],
                             [label] * len(idx)))
            t = np.array([float(touch_key.get(p, 0)) for p in pairs])
            w = 1.0 / (1.0 + t) ** bias
            total = w.sum()
            if total <= 0:
                pick = rng.choice(len(idx), size=k, replace=False)
            else:
                pick = rng.choice(len(idx), size=min(k, len(idx)),
                                  replace=False, p=w / total)
        else:
            pick = rng.choice(len(idx), size=k, replace=False)
        opp_df.loc[idx[pick], "in_commit"] = True
    return opp_df


def build_forecast_snapshot(cfg, opp_df):
    """WS7 (#14): forecast snapshot entity. committed_usd is the story's
    claim (actual x commit_ratio[qi]) - plan-like semantics, same
    philosophy as quota_plan; actual_usd is measured from the data."""
    spec = cfg.get("forecast")
    if not spec:
        return None
    labels = cfg["time_model"]["quarter_labels"]
    ratios = spec["commit_ratio_by_quarter"]
    won = opp_df[opp_df["stage"] == "Closed Won"]
    rows = []
    for qi, label in enumerate(labels):
        actual = float(won.loc[won["fiscal_quarter"] == label,
                               "realized_price"].sum())
        ratio = float(ratios[qi])
        rows.append({
            "fiscal_quarter": label,
            "committed_usd": round(actual * ratio, 2),
            "actual_usd": round(actual, 2),
            "commit_vs_actual_pct": round(ratio * 100.0, 2),
        })
    return pd.DataFrame(rows)


def _derive_motion(opp_df):
    """Canonical Revenue Motion classification (#22): an account's FIRST
    deal of any kind in the window is New Logo, every later one
    Expansion. Rows are emitted in chronological order, so a single pass
    with a seen-set is deterministic."""
    seen = set()
    motions = []
    for acct in opp_df["account_id"]:
        motions.append(NEW_LOGO if acct not in seen else EXPANSION)
        seen.add(acct)
    return motions


def build_capacity(cfg):
    """WS1 remainder (M5 iter 4): the canonical Rep entity plus the
    capacity_plan sheet from the optional config capacity block.

    Two frames:
      reps          - one row per rep ever on staff in the sim window
                      (initial cohort + net hires between quarters;
                      attrition is not modeled - no scenario needs it)
      capacity_plan - per unit x quarter: planned vs actual headcount,
                      ramping-rep count, ramp productivity, and the DERIVED
                      effective_capacity_pct = ((actual - ramping) +
                      ramping * ramp_pct/100) / plan * 100

    Effective capacity is where story #19's "headcount at 98% of plan but
    effective capacity 85-90%" lives: the shortfall AND the ramp drag are
    both relative to what the annual plan assumed (all heads fully
    productive). Like quota, this block adds sheets only - sampling streams
    untouched, so existing sessions reproduce byte-identically.
    """
    dim, units = _capacity_dimension(cfg)
    if not units:
        return None
    labels = cfg["time_model"]["quarter_labels"]
    name_rng = np.random.default_rng([int(cfg["seed"]), 8])

    def new_rep(seq, unit):
        first = str(name_rng.choice(REP_FIRST_NAMES))
        last = str(name_rng.choice(REP_LAST_NAMES))
        return {
            "rep_id": f"REP-{seq:04d}",
            "rep_name": f"{first} {last}",
            dim: unit,
            "hire_fiscal_quarter": None,  # tenured before the sim window
        }

    rep_rows = []
    cap_rows = []
    seq = 0
    for unit, spec in units.items():
        plan_hc = [int(v) for v in spec["headcount_plan"]]
        actual_hc = [int(v) for v in spec.get("headcount_actual") or plan_hc]
        ramping = [int(v) for v in spec.get(
            "ramping_reps_by_quarter") or [0] * len(labels)]
        ramp_prod = float(spec.get("ramp_productivity_pct", 100.0))
        prev = actual_hc[0]
        for _ in range(prev):
            seq += 1
            rep_rows.append(new_rep(seq, unit))
        for qi in range(1, len(labels)):
            hires = actual_hc[qi] - prev
            for _ in range(max(hires, 0)):
                seq += 1
                row = new_rep(seq, unit)
                row["hire_fiscal_quarter"] = labels[qi]
                rep_rows.append(row)
            prev = actual_hc[qi]
        for qi, label in enumerate(labels):
            productive = actual_hc[qi] - ramping[qi]
            eff = ((productive + ramping[qi] * ramp_prod / 100.0)
                   / plan_hc[qi] * 100.0)
            cap_rows.append({
                "fiscal_quarter": label,
                "plan_unit_type": dim,
                "plan_unit": unit,
                "headcount_plan": plan_hc[qi],
                "headcount_actual": actual_hc[qi],
                "ramping_reps": ramping[qi],
                "ramp_productivity_pct": ramp_prod,
                "effective_capacity_pct": round(eff, 2),
            })
    return {
        "reps": pd.DataFrame(rep_rows),
        "capacity_plan": pd.DataFrame(cap_rows),
    }


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


def _outlier_mask(opp_df, cfg):
    """Replay the in-loop whale selection ([seed, 3, qi] stream) to attach
    a persistent is_outlier flag (#25/#17). The replay is exact: whales
    were chosen per quarter from range(n_rows_that_quarter)."""
    spec = cfg["opportunities"].get("outlier_deals")
    if not spec:
        return None
    labels = cfg["time_model"]["quarter_labels"]
    shares = spec.get("share_by_quarter") or \
        [spec.get("share")] * len(labels)
    mask = pd.Series(False, index=opp_df.index)
    for qi, label in enumerate(labels):
        grp = opp_df.index[opp_df["fiscal_quarter"] == label]
        n = len(grp)
        if not n:
            continue
        k = max(1, int(round(n * float(shares[qi]))))
        k = min(k, n)
        wh_rng = np.random.default_rng([int(cfg["seed"]), 3, qi])
        pick = wh_rng.choice(n, size=k, replace=False)
        mask.loc[grp[pick]] = True
    return mask


def apply_raking(opp_df, cfg):
    """Deterministic monetary raking pass (WS3 aggregate targets).

    Per plan-unit x quarter stratum: scale list_price so closed-won
    realized revenue hits the quota target TIMES the unit's configured
    attainment ratio (default 1.0). This is what lets a story say
    "Enterprise missed plan by 5%" - the plan stays the plan, and actuals
    land at 95% of it. realized is recomputed from the scaled list,
    preserving the derived-field identity exactly.

    OPEN rows are NOT scaled (F25 live s11n): they carry no closed
    revenue, and scaling them made open-pipeline VALUE move with the
    plan, which made coverage_ratio mathematically unfixable by plan
    sizing - the documented contract says only closed-won revenue is
    raked. All CLOSED rows in a stratum scale together (won and lost),
    keeping the stratum's price distribution coherent. Margin fields
    survive: the cogs_ratio column is per-deal and unscaled, so
    margin_pct is invariant under uniform price scaling.
    """
    if not cfg.get("quota"):
        return opp_df
    quarters = cfg["time_model"]["quarter_labels"]
    dim, targets = _quota_dimension(cfg)
    attainment = cfg["quota"].get("attainment") or \
        cfg["quota"].get(f"attainment_by_{dim}") or \
        cfg["quota"].get("attainment_by_segment", {})
    # WS8 mixtures (#25): optional EX-WHALE attainment - the story's
    # underlying (core) rate distinct from the headline number whales
    # inflate. Two-step solve per stratum: core deals rake to
    # ex_outlier ratio, then whales scale to make the TOTAL hit the
    # headline ratio.
    ex_ratios = cfg["quota"].get("attainment_ex_outliers")
    df = opp_df.copy()
    if ex_ratios and "is_outlier" in df.columns:
        for unit, curve in targets.items():
            raw_ex = ex_ratios.get(unit)
            if raw_ex is None:
                continue  # no ex-whale claim for this unit -> legacy path
            raw_head = attainment.get(unit, 1.0)
            try:
                r_ex = float(raw_ex) if raw_ex is not None else None
                r_head = float(raw_head)
            except (TypeError, ValueError):
                continue
            for qi, label in enumerate(quarters):
                plan_t = float(curve[qi])
                m = (df[dim] == unit) & (df["fiscal_quarter"] == label)
                closed_m = m & df["stage"].isin(["Closed Won", "Closed Lost"])
                out_m = closed_m & df["is_outlier"]
                core_m = closed_m & ~df["is_outlier"]
                won_core = core_m & (df["stage"] == "Closed Won")
                won_out = out_m & (df["stage"] == "Closed Won")
                core_sum = df.loc[won_core, "realized_price"].sum()
                if plan_t <= 0 or core_sum <= 0:
                    continue
                # step 1: core -> ex-outlier target
                k_core = (plan_t * r_ex) / core_sum
                keep_c = 1 - df.loc[core_m, "discount_pct"] / 100
                df.loc[core_m, "list_price"] = (
                    df.loc[core_m, "list_price"] * k_core).round(2)
                df.loc[core_m, "realized_price"] = (
                    df.loc[core_m, "list_price"] * keep_c).round(2)
                resid = round(plan_t * r_ex -
                              df.loc[won_core, "realized_price"].sum(), 2)
                if resid:
                    idx = df.loc[won_core, "realized_price"].idxmax()
                    kf = 1 - df.at[idx, "discount_pct"] / 100
                    df.loc[idx, "list_price"] = round(
                        df.loc[idx, "list_price"] + resid / kf, 2)
                    df.loc[idx, "realized_price"] = round(
                        df.loc[idx, "list_price"] * kf, 2)
                # step 2: whales absorb the rest of the headline target
                whale_sum = df.loc[won_out, "realized_price"].sum()
                want_total = plan_t * r_head
                have_total = df.loc[won_core, "realized_price"].sum() + \
                    whale_sum
                if whale_sum > 0 and want_total > 0:
                    k_w = want_total / have_total
                    keep_w = 1 - df.loc[out_m, "discount_pct"] / 100
                    df.loc[out_m, "list_price"] = (
                        df.loc[out_m, "list_price"] * k_w).round(2)
                    df.loc[out_m, "realized_price"] = (
                        df.loc[out_m, "list_price"] * keep_w).round(2)
                    resid_w = round(
                        want_total -
                        df.loc[won_core, "realized_price"].sum() -
                        df.loc[won_out, "realized_price"].sum(), 2)
                    if resid_w:
                        idx = df.loc[won_out, "realized_price"].idxmax()
                        kf = 1 - df.at[idx, "discount_pct"] / 100
                        df.loc[idx, "list_price"] = round(
                            df.loc[idx, "list_price"] + resid_w / kf, 2)
                        df.loc[idx, "realized_price"] = round(
                            df.loc[idx, "list_price"] * kf, 2)
    for unit, curve in targets.items():
        raw_ratio = attainment.get(unit, 1.0)
        try:
            ratio = float(raw_ratio)
        except (TypeError, ValueError):
            ratio = 1.0  # defense in depth: never crash raking on a bad type
        if ex_ratios and ex_ratios.get(unit) is not None:
            continue  # handled by the mixture path above
        for qi, label in enumerate(quarters):
            target = float(curve[qi]) * ratio
            mask = (df[dim] == unit) & (df["fiscal_quarter"] == label)
            won_mask = mask & (df["stage"] == "Closed Won")
            scale_mask = mask & df["stage"].isin(
                ["Closed Won", "Closed Lost"])
            won_sum = df.loc[won_mask, "realized_price"].sum()
            if target <= 0 or won_sum <= 0:
                continue  # cannot rake an empty or unsellable stratum
            k = target / won_sum
            keep = 1 - df.loc[scale_mask, "discount_pct"] / 100
            df.loc[scale_mask, "list_price"] = (
                df.loc[scale_mask, "list_price"] * k).round(2)
            # recompute from the scaled list so realized == list*(1-d) exactly
            df.loc[scale_mask, "realized_price"] = (
                df.loc[scale_mask, "list_price"] * keep
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
    ownership_df, changed_by_q = build_ownership(cfg, accounts_df)
    opp_df = build_opportunities(
        cfg, accounts_df, rng,
        ownership=(ownership_df, changed_by_q)
        if ownership_df is not None else None)
    quota_df = build_quota_plan(cfg)
    # WS8 mixtures: persistent whale flag whenever outlier_deals is set
    if spec_outliers := cfg["opportunities"].get("outlier_deals"):
        opp_df["is_outlier"] = _outlier_mask(opp_df, cfg)
    # motion must exist BEFORE raking when the plan dimension is motion;
    # commit flags come AFTER (they depend on final actuals)
    if quota_df is not None and _quota_dimension(cfg)[0] == "motion":
        opp_df["motion"] = _derive_motion(opp_df)
    if quota_df is not None:
        opp_df = apply_raking(opp_df, cfg)
    activity_df = build_activity(cfg, accounts_df)
    if cfg.get("forecast"):
        opp_df = _apply_commit_flags(opp_df, cfg, activity_df)
        forecast_df = build_forecast_snapshot(cfg, opp_df)
    else:
        forecast_df = None
    summary_df = build_summary(opp_df, cfg["time_model"]["quarter_labels"])
    frames = {
        "accounts": accounts_df,
        "opportunities": opp_df,
        "quarterly_summary": summary_df,
    }
    if quota_df is not None:
        frames["quota_plan"] = quota_df
    cap_frames = build_capacity(cfg)
    if cap_frames is not None:
        frames.update(cap_frames)
    if ownership_df is not None:
        frames["account_ownership"] = ownership_df
    if activity_df is not None:
        frames["account_activity"] = activity_df
    if forecast_df is not None:
        frames["forecast_snapshot"] = forecast_df
    hist = opp_df.attrs.get("stage_history")
    if hist is not None:
        frames["opportunity_stage_history"] = hist
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
                   "quota_plan", "reps", "capacity_plan",
                   "account_ownership", "account_activity",
                   "forecast_snapshot", "opportunity_stage_history",
                   "_synngen_meta"]
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for name in sheet_order:
            if name in frames:
                frames[name].to_excel(writer, sheet_name=name, index=False)
        if meta is not None and "_synngen_meta" not in frames:
            meta.to_excel(writer, sheet_name="_synngen_meta", index=False)
    return out_path


def generate_to_workbook(cfg_or_path):
    """Convenience: generate and write in one call. Returns (frames, path)."""
    if isinstance(cfg_or_path, (str, Path)):
        cfg_path = Path(cfg_or_path)
        cfg = load_simulator(cfg_path)
        # R5 fix: relative output.workbook paths in a config FILE are
        # resolved against the config's own directory, not the process
        # cwd - `python -m syngen generate sessions/<date>_<slug>/...`
        # used to drop the workbook into <cwd>/output instead of the
        # session folder.
        wb = Path(cfg["output"]["workbook"])
        if not wb.is_absolute():
            cfg["output"]["workbook"] = str(
                (cfg_path.resolve().parent / wb).resolve())
    else:
        cfg = cfg_or_path
    frames = generate(cfg)
    path = write_workbook(frames, cfg["output"]["workbook"],
                          meta=_meta_frame(cfg))
    return frames, path
