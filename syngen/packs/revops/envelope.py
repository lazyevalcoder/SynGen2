"""Engine envelope registry (P8): the achievable range of each metric.

Acceptance is a *guarantee*, not a hope (see `docs/REALIZABILITY.md`).
The deterministic layer must never accept a target the generator cannot
produce, and must never write a config outside its own domain. Every
ceiling/floor the solvers and acceptance gates rely on lives here, in one
place, so `preflight` (what can be *solved*) and `criteria_lint` (what can
be *accepted*) agree by construction.

All functions are pure, config-driven, and free of story nouns or
scenario conditionals. Where a closed form is not available they use the
same seeded Monte-Carlo estimator the concentration solver uses, so a
"reachable" verdict from here matches what the solver will actually build.
"""
import numpy as np

# config.py: deal_size_lognormal.sigma must be in (0, 4.0]
SIGMA_CAP = 4.0
_OPEN_SEED = [20260824, 11]


def _labels(cfg):
    return cfg["time_model"]["quarter_labels"]


def n_open_deals(cfg):
    """Total open-pipeline deal count the config will generate."""
    o = cfg.get("opportunities") or {}
    labels = _labels(cfg)
    mults = o.get("volume_multipliers") or [1.0] * len(labels)
    shares = (cfg.get("pipeline") or {}).get("share_open_by_quarter") or []
    total = 0.0
    for qi in range(len(labels)):
        s = shares[qi] if qi < len(shares) else 0.0
        total += (float(o.get("per_quarter", 0)) * float(mults[qi])
                  * float(s))
    return int(total)


def pipeline_top_share(cfg, sigma, topn, outlier_mult=None):
    """Top-N account share of open-pipeline value (engine-faithful model).

    Mirrors the engine's construction: per quarter, draw iid lognormal deal
    sizes, scale a random `share_by_quarter` subset by the outlier
    multiplier, pick the open cohort uniformly, and assign accounts
    uniformly. Including the outlier lever matters - it is the engine's
    dominant concentration knob (multiplier is unbounded), so a sigma-only
    model badly under-predicts and would false-kill reachable targets
    (cert s21: sigma-only model predicted 52%, engine realized 96.9%).

    Returns a fraction in [0, 1], or None when the config is too small.
    """
    o = cfg.get("opportunities") or {}
    labels = _labels(cfg)
    n_acc = int((cfg.get("accounts") or {}).get("count", 0))
    if n_acc < 10:
        return None
    per_q = float(o.get("per_quarter", 0) or 0)
    mults = o.get("volume_multipliers") or [1.0] * len(labels)
    p_open = (cfg.get("pipeline") or {}).get("share_open_by_quarter") or []
    out = o.get("outlier_deals") or {}
    share_q = out.get("share_by_quarter") or []
    if not share_q and out.get("share") is not None:
        share_q = [out.get("share")] * len(labels)
    om = (float(outlier_mult) if outlier_mult is not None
          else float(out.get("multiplier", 1.0) or 1.0))
    rng = np.random.default_rng(_OPEN_SEED)
    tot = np.zeros(n_acc)
    n_total_open = 0
    for qi in range(len(labels)):
        n = int(round(per_q * float(mults[qi])))
        if n <= 0:
            continue
        sizes = rng.lognormal(0.0, float(sigma), n)
        s = float(share_q[qi]) if qi < len(share_q) else 0.0
        if om > 1.0 and s > 0:
            k = max(1, int(round(n * s)))
            idx = rng.choice(n, size=min(k, n), replace=False)
            sizes[idx] *= om
        po = float(p_open[qi]) if qi < len(p_open) else 0.0
        ko = min(int(round(n * po)), n)
        if ko <= 0:
            continue
        oi = rng.choice(n, size=ko, replace=False)
        acc = rng.integers(0, n_acc, ko)
        np.add.at(tot, acc, sizes[oi])
        n_total_open += ko
    if n_total_open < 10:
        return None
    ssum = float(tot.sum())
    if ssum <= 0:
        return None
    return float(np.sort(tot)[::-1][:int(topn)].sum() / ssum)


def pipeline_concentration_ceiling(cfg, topn, sigma_cap=SIGMA_CAP):
    """Top-N open-pipeline share at the sigma domain cap, with the config's
    CURRENT outlier multiplier. Reference only: the outlier multiplier is an
    unbounded lever (`config.py` requires only `> 1`), so this is not a hard
    ceiling - the solver can raise the multiplier to reach a target."""
    return pipeline_top_share(cfg, sigma_cap, topn)


def headline_growth_ceiling(cfg):
    """Max headline won-revenue growth (first -> last quarter), in percent.

    Closed-won revenue is RAKED to plan x attainment, so the growth rate is
    pinned by the plan curves, not by knobs. A `min_headline_growth_pct`
    above this ceiling is arithmetically unreachable. Returns 0.0 when no
    plan is present (the engine then has no growth lever at all).
    """
    quota = cfg.get("quota") or {}
    units = None
    for sub in ("by_segment", "by_territory", "by_motion"):
        if isinstance(quota.get(sub), dict) and quota[sub]:
            units = quota[sub]
            break
    if not units:
        return 0.0
    labels = _labels(cfg)
    qi = len(labels) - 1
    att = quota.get("attainment_by_segment") or quota.get("attainment") or {}
    try:
        first = sum(float(c[0]) * float(att.get(u, 1.0))
                    for u, c in units.items()
                    if isinstance(c, list) and c)
        last = sum(float(c[qi]) * float(att.get(u, 1.0))
                   for u, c in units.items()
                   if isinstance(c, list) and qi < len(c))
    except (TypeError, ValueError):
        return 0.0
    if first <= 0:
        return 0.0
    return (last / first - 1.0) * 100.0


def tier_share_ceiling(count_shares, mult, tier, floor=0.05):
    """Max achievable REVENUE share (%) for a tier at the drafted price
    multipliers (P6 P1.4). Shared by the acceptance lint and the capability
    service so both agree by construction."""
    if not count_shares or tier not in count_shares or not mult:
        return None
    others = [t for t in count_shares if t != tier]
    if not others:
        return 100.0
    count_c = max(0.0, 1.0 - floor * len(others))
    denom = count_c * float(mult.get(tier, 1.0)) + sum(
        floor * float(mult.get(t, 1.0)) for t in others)
    if denom <= 0:
        return 0.0
    return count_c * float(mult.get(tier, 1.0)) / denom * 100.0


def avg_price_by_tier(cfg, tier):
    """Estimated average realized price for a tier under raking (P5 WP6).

    With a quota block, closed-won revenue is raked to plan x attainment, so
    a tier's average realized price ~= (attained total / won count) scaled by
    the tier's relative price position. Returns None when the config lacks
    the inputs. Shared with the acceptance lint."""
    quota = cfg.get("quota")
    products = cfg.get("products") or {}
    catalog = products.get("catalog")
    opps = cfg.get("opportunities") or {}
    if not quota or not isinstance(catalog, list) or not catalog:
        return None
    labels = _labels(cfg)
    qi = len(labels) - 1
    by_seg, dim_name = None, "segment"
    for sub, dn in (("by_segment", "segment"), ("by_territory", "territory"),
                    ("by_motion", "motion")):
        if isinstance(quota.get(sub), dict):
            by_seg, dim_name = quota[sub], dn
            break
    if not isinstance(by_seg, dict):
        return None
    try:
        plan_total = sum(float(curve[qi]) for curve in by_seg.values()
                         if isinstance(curve, list) and qi < len(curve))
        att = quota.get("attainment_by_segment") or quota.get("attainment") or {}
        attained = sum(float(curve[qi]) * float(att.get(u, 1.0))
                       for u, curve in by_seg.items()
                       if isinstance(curve, list) and qi < len(curve))
        won_n = float(opps["per_quarter"]) * \
            float(opps.get("volume_multipliers", [1.0] * len(labels))[qi]) * \
            float(opps.get("win_rate", 0.3))
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    if won_n <= 0:
        return None
    avg_deal = attained / won_n if attained else plan_total / won_n
    mult = products.get("price_multiplier_by_tier") or {}
    shares = {}
    for e in catalog:
        t = e.get("tier")
        s = e.get("share")
        if isinstance(t, str) and isinstance(s, (int, float)):
            shares[t] = shares.get(t, 0.0) + float(s)
    if not shares or not mult or tier not in shares:
        return None
    total = sum(shares.values()) or 1.0
    count_shares = {t: s / total for t, s in shares.items()}
    denom = sum(count_shares.get(t, 0.0) * float(mult.get(t, 1.0))
                for t in count_shares)
    if denom <= 0:
        return None
    return avg_deal * float(mult.get(tier, 1.0)) / denom


def win_rate_noise_pp(cfg, z=2.0):
    """Two-sigma noise floor (percentage points) of a quarterly win rate.

    `win_rate_flat` asks the win rate to stay within a band; with N deals in
    a quarter the sample proportion has standard error sqrt(p(1-p)/N), so a
    band below z*SE*100 is not deterministically landable (cert s16 drafted
    +/-3pp on ~600 deals). Uses the SMALLEST quarter (most conservative).
    Returns None when the inputs are unusable."""
    import math
    o = cfg.get("opportunities") or {}
    labels = _labels(cfg)
    p = float(o.get("win_rate", 0.3) or 0.3)
    per_q = float(o.get("per_quarter", 0) or 0)
    mults = o.get("volume_multipliers") or [1.0] * len(labels)
    if per_q <= 0 or not (0.0 < p < 1.0) or not mults:
        return None
    n = min(per_q * float(m) for m in mults)
    if n <= 0:
        return None
    return z * math.sqrt(p * (1.0 - p) / n) * 100.0


def revenue_concentration_share(cfg, topn, sigma=None):
    """Top-N account share of WON revenue (reference estimator, P13).

    Mirrors the engine: per quarter draw lognormal won deals, scale an
    outlier subset, assign accounts uniformly. Reference only - the outlier
    multiplier is an unbounded lever, so this is not a hard ceiling."""
    o = cfg.get("opportunities") or {}
    labels = _labels(cfg)
    n_acc = int((cfg.get("accounts") or {}).get("count", 0))
    if n_acc < 10:
        return None
    per_q = float(o.get("per_quarter", 0) or 0)
    mults = o.get("volume_multipliers") or [1.0] * len(labels)
    wr = float(o.get("win_rate", 0.3) or 0.3)
    sig = (sigma if sigma is not None else
           float((o.get("deal_size_lognormal") or {}).get("sigma", 0.6) or 0.6))
    out = o.get("outlier_deals") or {}
    share_q = out.get("share_by_quarter") or []
    if not share_q and out.get("share") is not None:
        share_q = [out.get("share")] * len(labels)
    om = float(out.get("multiplier", 1.0) or 1.0)
    rng = np.random.default_rng(_OPEN_SEED)
    tot = np.zeros(n_acc)
    n_total = 0
    for qi in range(len(labels)):
        n = int(round(per_q * float(mults[qi])))
        if n <= 0:
            continue
        sizes = rng.lognormal(0.0, sig, n)
        s = float(share_q[qi]) if qi < len(share_q) else 0.0
        if om > 1.0 and s > 0:
            k = max(1, int(round(n * s)))
            idx = rng.choice(n, size=min(k, n), replace=False)
            sizes[idx] *= om
        kw = min(int(round(n * wr)), n)
        if kw <= 0:
            continue
        wi = rng.choice(n, size=kw, replace=False)
        acc = rng.integers(0, n_acc, kw)
        np.add.at(tot, acc, sizes[wi])
        n_total += kw
    if n_total < 10:
        return None
    ssum = float(tot.sum())
    if ssum <= 0:
        return None
    return float(np.sort(tot)[::-1][:int(topn)].sum() / ssum)


def deal_size_ratio(cfg):
    """Q4/Q1 median won deal-size ratio the config implies, or None."""
    o = cfg.get("opportunities") or {}
    ls = o.get("deal_size_lognormal") or {}
    med = ls.get("medians_by_quarter")
    if isinstance(med, list) and len(med) >= 2 and float(med[0]) > 0:
        return float(med[-1]) / float(med[0])
    return None
