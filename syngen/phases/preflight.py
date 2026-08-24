"""Pre-flight calibration (M5 iter 3, F17).

The dominant live failure mode is no longer the convergence loop - it is
the DRAFTER's first shot: schema-valid configs whose arithmetic misses
pinned levels by several pp, references plan units that don't exist, or
contradicts raking mechanics. Each such defect used to cost a full
convergence session to discover.

This module deterministically cross-checks a drafted simulator.json
against the approved criteria BEFORE generation starts:

- P1 referential (HARD): criteria reference units/tiers/regions/dimensions
  that must exist in the config - their absence guarantees structural
  escalation later, so failing fast saves the whole session.
- P2 level arithmetic (SOFT): predicted quarterly levels from the same
  transfer functions the knob playbook uses, compared against pinned
  targets.
- P3 contradictions (SOFT): known mechanical conflicts (deal-size trend
  under raking without volume levers, mix-shift targets on static shares).

HARD failures trigger ONE corrective re-draft; persistent HARD failures
abort before any iteration burns. SOFT findings are logged loudly so the
human at Gate 2 understands why convergence may be slow.
"""
import copy
import json

import numpy as np
import pandas as pd

from syngen.config import ConfigError, validate_simulator_doc

TIER_CHECKS = {"tier_share_shift", "discount_margin_link",
               "avg_price_by_tier", "blended_margin_trend"}
QUARTER_LEVEL_CHECKS = {"avg_discount_quarter", "realized_vs_list"}


def _region_weights(cfg):
    """Mean weight per region (curves averaged, mirroring the engine)."""
    weights = {}
    for name, val in cfg["accounts"].get("regions", {}).items():
        if isinstance(val, dict):
            curve = val.get("weights_by_quarter") or [1.0]
            weights[name] = sum(float(w) for w in curve) / len(curve)
        else:
            weights[name] = float(val)
    total = sum(weights.values()) or 1.0
    return {k: v / total for k, v in weights.items()}


def _tier_revenue_shares_at(cfg, qi):
    """Approximate per-quarter revenue share per tier: count share at
    quarter qi times price multiplier, normalized (rev_share calculus)."""
    prods = cfg.get("products")
    if not prods:
        return {}
    pmult = prods.get("price_multiplier_by_tier", {})
    weighted = {}
    for p in prods.get("catalog", []):
        share = p.get("share")
        if isinstance(share, dict):
            curve = share.get("weights_by_quarter") or [1.0]
            count_share = float(curve[qi]) if qi < len(curve) else \
                sum(float(w) for w in curve) / len(curve)
        else:
            count_share = float(share or 0.0)
        weighted[p["tier"]] = weighted.get(p["tier"], 0.0) + \
            count_share * float(pmult.get(p["tier"], 1.0))
    total = sum(weighted.values())
    if total <= 0:
        return {}
    return {t: w / total for t, w in weighted.items()}


def _quarter_tier_term(cfg, qi):
    """Per-quarter discount-delta contribution (revenue shares vary with
    mix-shift curves - using static Q1 shares mispredicted levels by >2pp
    on live s20)."""
    if not cfg.get("products"):
        return 0.0
    dd = cfg["products"].get("discount_delta_pp_by_tier", {})
    rs = _tier_revenue_shares_at(cfg, qi)
    return sum(rs.get(t, 0.0) * float(v) for t, v in dd.items())


def _predicted_discount_curve(cfg):
    """Predicted blended won-discount per quarter index (playbook formula
    incl. the per-quarter tier-delta term)."""
    dspec = cfg["opportunities"]["discount"]
    rw = _region_weights(cfg)
    n_q = len(cfg["time_model"]["quarter_labels"])
    eoq = cfg["opportunities"]["close_clustering"][
        "share_in_end_of_quarter_window"]
    boost = dspec["end_of_quarter_boost_pp"]
    curve = []
    for qi in range(n_q):
        base = sum(rw[r] * float(vals[qi]) for r, vals
                   in dspec["base_by_quarter"].items())
        curve.append(base + eoq * boost + _quarter_tier_term(cfg, qi))
    return curve


def calibrate(cfg, criteria_doc):
    """Cross-check drafted config against criteria. Returns findings:
    list of dicts {rule, severity: 'HARD'|'SOFT', criterion, msg}."""
    findings = []
    try:
        validate_simulator_doc(json.loads(json.dumps(cfg)))
    except ConfigError as e:
        # lint gate should have caught this; still, never crash pre-flight
        add = lambda rule, severity, criterion, msg: findings.append(  # noqa: E731
            {"rule": rule, "severity": severity, "criterion": criterion,
             "msg": msg})
        add("PF0", "HARD", "*", f"config invalid: {e}")
        return findings
    labels = cfg["time_model"]["quarter_labels"]
    label_set = set(labels)

    def add(rule, severity, criterion, msg):
        findings.append({"rule": rule, "severity": severity,
                         "criterion": criterion, "msg": msg})

    quota = cfg.get("quota") or {}
    plan_units = set(quota.get("by_segment") or quota.get("by_territory") or {})
    plan_dim = "segment" if quota.get("by_segment") else "territory"
    territory_names = set((cfg["accounts"].get("territories") or {}))
    tier_names = {p.get("tier") for p in
                  cfg.get("products", {}).get("catalog", [])}
    has_products = bool(cfg.get("products"))

    disc_curve = None
    for c in criteria_doc["criteria"]:
        cid, check, params = c["id"], c["check"], c.get("params", {})

        # P1: every criterion-quarter must exist in the configured calendar
        # (live s20 draw: criteria said FY25, config said FY26 - every
        # quarter-scoped check silently returned nan)
        for key, val in params.items():
            if isinstance(val, str) and \
                    __import__("re").match(r"^FY\d{2,4}-Q\d$", val) \
                    and val not in label_set:
                add("PF1", "HARD", cid,
                    f"quarter '{val}' ({key}) is not in the config "
                    f"calendar {labels}")

        if check in ("revenue_vs_plan", "gap_concentration",
                     "coverage_ratio"):
            if not quota:
                add("PF1", "HARD", cid,
                    f"{check} criterion but no quota block in config - "
                    "guaranteed structural failure")
                continue
            seg = params.get("segment")
            dim = params.get("dimension",
                             "territory" if quota.get("by_territory")
                             else "segment")
            # unit checks only apply to criteria that NAME a plan unit
            # (coverage_ratio is typically company-wide and quarter-scoped)
            if seg is None:
                continue
            if dim != plan_dim:
                add("PF1", "HARD", cid,
                    f"criterion dimension '{dim}' but plan uses "
                    f"'{plan_dim}' units")
            elif seg not in ("_all_",) and seg not in plan_units:
                add("PF1", "HARD", cid,
                    f"criterion unit '{seg}' not in plan units "
                    f"{sorted(plan_units)}")

        if check == "gap_concentration":
            if not quota:
                add("PF1", "HARD", cid,
                    "gap_concentration criterion but no quota block")
                continue
            dim = params.get("dimension",
                             "territory" if quota.get("by_territory")
                             else "segment")
            known = territory_names if dim == "territory" else \
                set(cfg["accounts"].get("segments", {}))
            # units come from the plan itself
            if plan_dim != dim:
                add("PF1", "HARD", cid,
                    f"criterion dimension '{dim}' but plan uses "
                    f"'{plan_dim}' units")

        if check == "region_discount_premium":
            known_regions = set(cfg["opportunities"]["discount"]
                                ["base_by_quarter"])
            for r in [params.get("region"), *(params.get("vs") or [])]:
                if r not in known_regions:
                    add("PF1", "HARD", cid,
                        f"region '{r}' not in discount.base_by_quarter "
                        f"(known: {sorted(known_regions)})")

        if check in TIER_CHECKS:
            if not has_products:
                add("PF1", "HARD", cid,
                    f"{check} criterion but no products block in config")
                continue
            for key in ("tier", "high_margin_tier", "low_margin_tier"):
                t = params.get(key)
                if t and t not in tier_names:
                    add("PF1", "HARD", cid,
                        f"tier '{t}' not in product catalog "
                        f"(known: {sorted(t for t in tier_names if t)})")

        if check == "icp_creation_shift":
            if cfg["accounts"].get("icp_share") in (None, 0) and \
                    not cfg["accounts"].get("icp_sampling_weights_by_quarter"):
                add("PF3", "SOFT", cid,
                    "no icp_share/icp_sampling_weights configured - icp "
                    "column will be all-false and the check fails "
                    "structurally")

        # --- P2 level arithmetic ---
        if check in QUARTER_LEVEL_CHECKS and disc_curve is None:
            try:
                disc_curve = _predicted_discount_curve(cfg)
            except (KeyError, TypeError, ValueError):
                pass
        if check == "tier_share_shift" and has_products:
            tier = params.get("tier")
            labels_idx = {l: i for i, l in enumerate(labels)}
            for qkey, want_key in (("quarter_start", "from_share_pct"),
                                   ("quarter_end", "to_share_pct")):
                qlabel = params.get(qkey) if params.get(qkey) in label_set \
                    else (labels[0] if qkey == "quarter_start" else
                          labels[-1])
                want = params.get(want_key)
                if want is None:
                    continue
                try:
                    pred = _tier_revenue_shares_at(
                        cfg, labels.index(qlabel)).get(tier, 0.0) * 100
                except Exception:  # noqa: BLE001 - approximation only
                    continue
                off = abs(pred - float(want))
                if off > 6.0:
                    add("PF1", "HARD", cid,
                        f"tier '{tier}' predicted revenue share ~{pred:.0f}% "
                        f"in {qlabel} vs criterion ~{want:g}% ({off:.0f}pp "
                        "off) - catalog shares/multipliers mis-sized")
                elif off > 3.0:
                    add("PF2", "SOFT", cid,
                        f"tier '{tier}' predicted share ~{pred:.0f}% vs "
                        f"~{want:g}% ({off:.1f}pp off)")
        if check == "avg_discount_quarter":
            q = params.get("quarter")
            if q in label_set and disc_curve:
                qi = labels.index(q)
                pred = disc_curve[qi]
                want = float(params.get("target_pct", 0))
                off = abs(pred - want)
                if off > 1.5:
                    add("PF2", "SOFT", cid,
                        f"predicted Q{qi + 1} avg discount ~{pred:.1f}% vs "
                        f"criterion {want:g}% ({off:.1f}pp off)")
        if check == "realized_vs_list":
            if disc_curve:
                pairs = [("quarter_start", "target_start_pct"),
                         ("quarter_end", "target_end_pct")]
                for qkey, tkey in pairs:
                    q, want = params.get(qkey), params.get(tkey)
                    if q in label_set and want is not None:
                        qi = labels.index(q)
                        implied = 100 - disc_curve[qi] + 1.8
                        off = abs(implied - float(want))
                        if off > 1.5:
                            add("PF2", "SOFT", cid,
                                f"predicted {q} realized/list ~{implied:.1f}%"
                                f" vs criterion {want:g}% ({off:.1f}pp off)")

        # --- P3 contradictions ---
        if check == "deal_size_trend" and quota and \
                not cfg["opportunities"].get("volume_multipliers"):
            add("PF3", "SOFT", cid,
                "deal_size_trend under a quota block without "
                "volume_multipliers: raking pins totals so average size "
                "cannot move - expect this criterion to fight the plan")
        if check == "tier_share_shift" and has_products:
            moves = float(params.get("from_share_pct", 0)) != \
                float(params.get("to_share_pct", 0))
            all_static = all(not isinstance(p.get("share"), dict)
                             for p in cfg["products"]["catalog"])
            if moves and all_static:
                add("PF3", "SOFT", cid,
                    "mix-shift criterion but every catalog share is a "
                    "static scalar - needs weights_by_quarter curves")
        if check == "coverage_ratio" and cfg.get("pipeline"):
            # P1: quarter+offset must land inside the calendar (normally
            # pre-repaired by repair_criteria - this is the backstop)
            q = params.get("quarter")
            if q in label_set:
                k = labels.index(q) + int(
                    params.get("target_quarter_offset", 0))
                if not (0 <= k < len(labels)):
                    add("PF1", "HARD", cid,
                        f"target_quarter_offset points outside the "
                        f"calendar ({q} + "
                        f"{params.get('target_quarter_offset')})")
            # open pipeline that provides coverage at quarter k is, by
            # the engine's date model, at least p_k stale - if that
            # already exceeds the stage_aging cap the two criteria
            # cannot BOTH pass (live s11i)
            aging = [oc for oc in criteria_doc["criteria"]
                     if oc["check"] == "stage_aging"]
            if aging and q in label_set:
                k = labels.index(q) + int(
                    params.get("target_quarter_offset", 0))
                if 0 <= k < len(labels):
                    cap = float(aging[0]["params"].get(
                        "max_stale_share_pct", 35)) / 100.0
                    thr = float(aging[0]["params"].get(
                        "stale_threshold_days", 120))
                    p_k = _pipeline_stale_probs(cfg, thr)[k]
                    if p_k > cap:
                        add("PF3", "SOFT", cid,
                            f"coverage at {q} needs open pipeline that "
                            f"is ~{p_k * 100:.0f}% stale (engine model) "
                            f"vs stage_aging cap {cap * 100:.0f}% - the "
                            "two claims conflict unless durations or "
                            "the threshold change")

    return findings


def hard_findings(findings):
    return [f for f in findings if f["severity"] == "HARD"]


def render_findings(findings):
    return "\n".join(f"  [{f['severity']}/{f['rule']}] "
                     f"{f['criterion']}: {f['msg']}" for f in findings)


# --- deterministic auto-calibration (M5 iter 3) -----------------------------
#
# The share calculus and pinned-level arithmetic are CLOSED-FORM. Asking
# the drafter to hit them is a coin flip; solving them here is exact.
# autocalibrate() patches the config BEFORE any LLM corrective loop runs.


def _set_count_share(cfg, tier, qi, count_share):
    """Set one tier's count share at quarter qi, rebalancing siblings."""
    prods = cfg["products"]
    catalog = prods["catalog"]
    idx = next(i for i, p in enumerate(catalog) if p["tier"] == tier)
    pmult = prods.get("price_multiplier_by_tier", {})
    m_t = float(pmult.get(tier, 1.0))

    def cshare(p, q):
        s = p.get("share")
        if isinstance(s, dict):
            curve = s.get("weights_by_quarter") or [1.0]
            return float(curve[q]) if q < len(curve) else \
                sum(float(w) for w in curve) / len(curve)
        return float(s or 0.0)

    others_w = sum(cshare(p, qi) * float(pmult.get(p["tier"], 1.0))
                   for j, p in enumerate(catalog) if j != idx)
    cs = max(0.01, min(0.97, count_share))
    # others must fill (1 - s): scale their count shares proportionally
    others_total_c = sum(cshare(p, qi) for j, p in enumerate(catalog)
                         if j != idx)
    target_others = (1.0 - cs)
    factor = target_others / others_total_c if others_total_c > 0 else 1.0
    for j, p in enumerate(catalog):
        if j == idx:
            continue
        s = p.get("share")
        if isinstance(s, dict):
            s["weights_by_quarter"][qi] = \
                float(s["weights_by_quarter"][qi]) * factor
        elif s is not None:
            p["share"] = float(s) * factor
            # promote scalar to flat curve so later quarters stay editable
            n_q = len(cfg["time_model"]["quarter_labels"])
            p["share"] = {"weights_by_quarter": [p["share"]] * n_q}
    p_t = catalog[idx]
    s = p_t.get("share")
    if isinstance(s, dict):
        s["weights_by_quarter"][qi] = cs
    else:
        n_q = len(cfg["time_model"]["quarter_labels"])
        p_t["share"] = {"weights_by_quarter": [cs] * n_q}


def autocalibrate(cfg, criteria_doc):
    """Deterministically patch pinned levels and tier-mix shares.
    Returns a list of human-readable fixes applied (empty = nothing done)."""
    fixes = []
    labels = cfg["time_model"]["quarter_labels"]
    dspec = cfg["opportunities"]["discount"]
    eoq = cfg["opportunities"]["close_clustering"][
        "share_in_end_of_quarter_window"]
    boost = dspec["end_of_quarter_boost_pp"]
    rw = _region_weights(cfg)

    def tier_term(qi=0):
        return _quarter_tier_term(cfg, qi)

    def bases_sum_at(qi):
        return sum(rw[r] * float(vals[qi])
                   for r, vals in dspec["base_by_quarter"].items())

    # NOTE ordering: tier-mix shares first (they shift revenue weights,
    # which feeds the discount tier-term), then pinned discount levels.
    # Tier solving runs TWICE: a multiplier adjustment in one quarter
    # changes every other quarter's achievable share, so counts must
    # re-solve against the final multipliers before levels are solved.
    for mode in ("tier", "tier", "levels", "planning", "margin",
                 "pipeline", "coverage"):
        _autocalibrate_pass(cfg, criteria_doc, labels, dspec, eoq, boost,
                            rw, fixes, mode=mode,
                            tier_term=tier_term, bases_sum_at=bases_sum_at)
    # renormalize product shares after edits
    _renormalize_product_shares_cfg(cfg)
    return fixes


def _autocalibrate_planning(cfg, criteria_doc, fixes):
    """Synthesize quota attainment from revenue_vs_plan / gap_concentration
    criteria (live s18: drafter omitted attainment entirely, and a
    gap-concentration story needs HETEROGENEOUS per-unit ratios anyway -
    uniform attainment makes concentration impossible)."""
    quota = cfg.get("quota")
    if not quota:
        # synthesize a naturally-sized plan when a criterion requires one
        # but the drafter omitted the whole block (live s11b: coverage_ratio
        # without quota is unfixable in-loop - quota is plan-of-record)
        needs_quota = any(
            c["check"] in ("revenue_vs_plan", "gap_concentration",
                           "coverage_ratio")
            for c in criteria_doc["criteria"])
        if not needs_quota:
            return
        o = cfg["opportunities"]
        n_q = len(cfg["time_model"]["quarter_labels"])
        natural = (o["per_quarter"] * o["win_rate"]
                   * float(o["deal_size_lognormal"]["median_usd"])
                   * 0.85)
        segments = cfg["accounts"].get("segments") or {"All": 1.0}
        weights = {}
        for name, val in segments.items():
            w = val.get("weights_by_quarter") if isinstance(val, dict) \
                else None
            weights[name] = (sum(float(x) for x in w) / len(w)) if w \
                else float(val)
        tot = sum(weights.values()) or 1.0
        cfg["quota"] = {
            "by_segment": {name: [round(natural * weights[name] / tot, 2)]
                           * n_q for name in segments},
            "attainment": {},
        }
        fixes.append("planning: synthesized a naturally-sized quota block "
                     f"across {len(segments)} segment(s) - criteria "
                     "require a plan to exist")
        quota = cfg["quota"]
    units = list(quota.get("by_segment") or quota.get("by_territory") or {})
    if not units:
        return
    att = quota.setdefault(
        "attainment", quota.setdefault("attainment_by_segment", {}))
    unit_targets = {}
    all_target = None
    gap_params = None
    for c in criteria_doc["criteria"]:
        p = c.get("params", {})
        if c["check"] == "revenue_vs_plan":
            seg = p.get("segment")
            want = float(p.get("target_pct", 100.0)) / 100.0
            if seg == "_all_":
                all_target = want
            else:
                unit_targets[seg] = want
        elif c["check"] == "gap_concentration":
            gap_params = p
    if gap_params is not None:
        # bottom quartile lags by 25pp, top quartiles over-attain to keep
        # the mean at the overall target -> concentrated shortfall by design
        t = all_target if all_target is not None else 1.0
        ordered = sorted(units)
        k = max(1, int(np.ceil(len(ordered) * 0.25)))
        low = round(max(0.05, t - 0.25), 4)
        high = round(min(1.35, (t * len(ordered) - k * low)
                         / max(1, len(ordered) - k)), 4) \
            if len(ordered) > k else t
        for i, u in enumerate(ordered):
            att[u] = low if i < k else high
        fixes.append(f"planning: synthesized heterogeneous attainment "
                     f"(laggards {low}, others {high}) for "
                     f"{gap_params.get('dimension', 'territory')} "
                     "gap-concentration claim")
    for unit, want in unit_targets.items():
        if unit in units and abs(float(att.get(unit, 1.0)) - want) > 0.01:
            att[unit] = round(want, 4)
            fixes.append(f"planning: set '{unit}' attainment to {want:.2f}")
    if not gap_params and all_target is not None:
        for unit in units:
            if abs(float(att.get(unit, 1.0)) - all_target) > 0.01:
                att[unit] = round(all_target, 4)
                fixes.append(f"planning: set '{unit}' attainment to "
                             f"{all_target:.2f} for company-wide target")


def _predicted_blended_margin(cfg, qi):
    """Approximate blended gross margin % for quarter qi from the margin
    map, tier revenue shares and the predicted discount level."""
    prods = cfg.get("products")
    if not prods:
        return None
    margins = prods["margin_by_tier"]
    shares = _tier_revenue_shares_at(cfg, qi)
    if not shares:
        return None
    avg_cogs = sum(shares.get(t, 0.0) * (1.0 - float(m))
                   for t, m in margins.items())
    disc = _predicted_discount_curve(cfg)[qi] / 100.0
    return 100.0 - avg_cogs / max(1e-6, 1.0 - disc)


def _autocalibrate_margin(cfg, criteria_doc, labels, fixes):
    """Solve blended_margin_trend by scaling the cogs SPREAD between
    tiers. With m_t = min_m + (v_t-min_m)*k, each quarter's cost mass is
    C_q(k) = P_q - k*Q_q, so the margin delta is LINEAR in k - solve
    exactly rather than searching."""
    prods = cfg.get("products")
    if not prods:
        return
    base_m = copy.deepcopy(prods["margin_by_tier"])
    min_m = min(base_m.values())
    for c in criteria_doc["criteria"]:
        if c["check"] != "blended_margin_trend":
            continue
        params = c.get("params", {})
        want = float(params["target_change_pct"])
        tol = float(params.get("tolerance_pp", 2.0))

        def cost_mass(qi, k):
            shares = _tier_revenue_shares_at(cfg, qi)
            tot = 0.0
            for t, m in base_m.items():
                a_t = 1.0 - min_m          # cogs at k=0
                b_t = m - min_m            # spread component
                tot += shares.get(t, 0.0) * (a_t - b_t * k)
            return tot

        d1 = _predicted_discount_curve(cfg)[0] / 100.0
        d4 = _predicted_discount_curve(cfg)[len(labels) - 1] / 100.0
        delta0 = (cost_mass(0, 0.0) / (1 - d1)
                  - cost_mass(len(labels) - 1, 0.0) / (1 - d4))
        slope = (-cost_mass(0, 1.0) / (1 - d1)
                 + cost_mass(len(labels) - 1, 1.0) / (1 - d4))
        if abs(slope) < 1e-9:
            continue
        k = (want - delta0) / slope
        # keep every margin inside (0.02, 0.95)
        k_max = 1e9
        for t, m in base_m.items():
            if m > min_m:
                k_max = min(k_max, (0.95 - min_m) / (m - min_m),
                            (min_m - 0.02) / (m - min_m) + 1.0)
        k = max(0.02, min(k_max, k))
        new_m = {t: round(min(0.95, max(0.02,
                 min_m + (m - min_m) * k)), 4) for t, m in base_m.items()}
        cfg["products"]["margin_by_tier"] = new_m
        got = (_predicted_blended_margin(cfg, len(labels) - 1)
               - _predicted_blended_margin(cfg, 0))
        fixes.append(f"{c['id']}: scaled margin spread (x{k:.2f}) -> "
                     f"predicted {got:+.1f}pp blended margin change "
                     f"(target {want:+g}pp)")


def _pipeline_stale_probs(cfg, thr):
    """Exact expected stale fraction per quarter, replicating the
    ENGINE's date-draw model: close offsets are a mixture (early vs
    end-of-quarter window) and created = close - duration, so ages at
    the last quarter end are D_qi - offset + duration. Monte Carlo on a
    fixed calibration seed -> a deterministic function of the config
    alone (F25: bounds approximations underpredicted ~8pp because EOQ
    clustering skews deal ages old beyond any uniform-bounds model)."""
    o = cfg["opportunities"]
    tm = cfg["time_model"]
    ends = [pd.Timestamp(d) for d in tm["quarter_end_dates"]]
    dspec = o["discount"]
    window = int(dspec["end_of_quarter_window_days"])
    eoq_share = float(o["close_clustering"][
        "share_in_end_of_quarter_window"])
    dd = o["deal_duration_days"]
    n_draws = 120_000
    probs = []
    for qi in range(len(ends)):
        q_start = ends[qi] - pd.DateOffset(months=3) + pd.Timedelta(days=1)
        q_len = (ends[qi] - q_start).days + 1
        # age at ref = (ref - close) + duration, close = q_start + offset
        # -> measure from quarter START (live s11h/s11i: measuring from
        # quarter END underpredicted by ~one full quarter of mass)
        days_to_ref = (ends[-1] - q_start).days
        rng = np.random.default_rng([20260824, 9, qi])
        early = rng.integers(0, max(1, q_len - window), size=n_draws)
        eoqw = rng.integers(max(1, q_len - window), q_len, size=n_draws)
        off = np.where(rng.random(n_draws) < eoq_share, eoqw, early)
        if isinstance(dd, dict):
            means = dd.get("means") or [30.0]
            mean_d = float(means[qi]) if qi < len(means) \
                else float(np.mean(means))
            dur = np.clip(np.round(rng.normal(
                mean_d, float(dd.get("spread", 10)), n_draws)), 1, None)
        else:
            dur = rng.integers(int(dd[0]), int(dd[1]), size=n_draws)
        ages = days_to_ref - off + dur
        probs.append(float((ages > thr).mean()))
    return probs


def _solve_open_shares(shares, probs, cap):
    """Exponential tilt s'_q ∝ s_q · exp(-β·p_q): monotonically shifts
    open-pipeline mass toward fresh quarters while preserving relative
    shape. Binary search the smallest β whose predicted blended stale
    share meets an 0.85x-safety target (the model is engine-exact, so a
    slim margin suffices). Every share keeps a FLOOR of
    25% of its original relative weight (live s11i: an unfloored tilt
    zeroed early quarters, which later passes then treated as 'no open
    pipeline exists' and scaled plans to $0 -> invalid config)."""
    target = cap * 0.85
    orig = np.asarray(shares, dtype=float)

    def floored_blend(beta):
        w = orig * np.exp(-beta * np.asarray(probs))
        tot = w.sum()
        w = w / tot if tot > 0 else np.full(len(shares), 1.0 / len(shares))
        w = np.maximum(w, 0.25 * orig)
        return w / w.sum()

    cur = floored_blend(0.0)
    if float((cur * probs).sum()) <= target:
        return None  # already comfortably inside the cap
    hi = 40.0
    pred_hi = float((floored_blend(hi) * probs).sum())
    if pred_hi > cap:
        # cannot meet the cap by redistribution alone (every quarter is
        # stale) - apply a moderate tilt only, and let the loop escalate
        # honestly rather than wrecking the open-pipeline shape
        w = floored_blend(2.0)
        return [round(float(v), 4) for v in w]
    lo = 0.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if float((floored_blend(mid) * probs).sum()) > target:
            lo = mid
        else:
            hi = mid
    w = floored_blend(hi)
    return [round(float(v), 4) for v in w]


def repair_criteria(cfg, doc):
    """Deterministic criteria repair for unanchorable references
    (live s11j: decomposer drafted target_quarter_offset=-1 from FY26-Q1,
    which points BEFORE the calendar - no config re-draft can fix that).
    Drops out-of-range target_quarter_offsets so the claim measures
    against its own quarter instead. Returns human-readable notes."""
    labels = cfg["time_model"]["quarter_labels"]
    notes = []
    for c in doc.get("criteria", []):
        p = c.get("params", {})
        off = p.get("target_quarter_offset")
        if not off or p.get("quarter") not in labels:
            continue
        k = labels.index(p["quarter"]) + int(off)
        if not (0 <= k < len(labels)):
            del p["target_quarter_offset"]
            notes.append(f"{c['id']}: dropped target_quarter_offset "
                         f"({off} from {p['quarter']} is outside the "
                         "calendar) - measuring against the quarter's "
                         "own plan")
    return notes


def _scaled_durations(dd, f):
    if isinstance(dd, dict):
        out = copy.deepcopy(dd)
        if out.get("means"):
            out["means"] = [max(1, round(float(m) * f))
                            for m in out["means"]]
        if out.get("spread") is not None:
            out["spread"] = round(float(out["spread"]) * f, 1)
        return out
    return [max(1, round(float(dd[0]) * f)), max(2, round(float(dd[1]) * f))]


def _coverage_constraints(cfg, criteria_doc):
    """Effective (quarter_index -> min_multiple) map from coverage_ratio
    criteria. Multiple criteria on the same effective quarter collapse
    to the STRONGEST multiple."""
    labels = cfg["time_model"]["quarter_labels"]
    out = {}
    for c in criteria_doc["criteria"]:
        if c["check"] != "coverage_ratio":
            continue
        p = c.get("params", {})
        q = p.get("quarter")
        if q not in labels:
            continue
        k = labels.index(q) + int(p.get("target_quarter_offset", 0))
        if 0 <= k < len(labels):
            out[k] = max(out.get(k, 0.0), float(p["min_multiple"]))
    return out


def _pipeline_joint_solve(cfg, aging_c, cov, fixes):
    """Joint solve when BOTH stage_aging and coverage_ratio exist
    (live s11k: they pull share_open_by_quarter in OPPOSITE directions,
    and plan scaling provably cannot change coverage because raking
    scales open rows with their stratum).

    Model (n uniform per quarter, deal-value factors cancel against the
    raked plan): coverage_k ~= sum_{q<=k} s_q / (att * w) >= m_k, i.e.
    each criterion imposes a LOWER BOUND on cumulative open share;
    staleness imposes sum(s_q*p_q)/sum(s_q) <= cap.

    Levers, in order: reshape shares (coverage mass placed as late in
    its prefix as possible, fresh last quarter tops up), then lower
    win_rate (unmeasured by any check), then shorten durations."""
    p = aging_c.get("params", {})
    cap = float(p.get("max_stale_share_pct", 35)) / 100.0
    thr = float(p.get("stale_threshold_days", 120))
    cid = aging_c["id"]
    o = cfg["opportunities"]
    n = len(cfg["time_model"]["quarter_end_dates"])
    mults = o.get("volume_multipliers") or [1.0] * n

    def n_q(qi):
        base = o["per_quarter"] * mults[qi]
        return base

    def current_state():
        s = [float(v) for v in cfg["pipeline"]["share_open_by_quarter"]]
        probs = _pipeline_stale_probs(cfg, thr)
        blend = sum(a * b for a, b in zip(s, probs)) / sum(s)
        cov_ok = True
        cum = 0.0
        for k in sorted(cov):
            cum = sum(float(x) * n_q(qi) for qi, x in enumerate(s[:k + 1]))
            plan_side = float(o["win_rate"]) * n_q(k)
            if cum < cov[k] * plan_side * 1.06:   # 6% slip safety
                cov_ok = False
                break
        return s, probs, blend, cov_ok

    s0, probs0, blend0, cov0_ok = current_state()
    if blend0 <= cap * 0.9 and cov0_ok:
        return  # drafted config already jointly feasible

    orig_w = float(o["win_rate"])
    orig_dd = copy.deepcopy(o["deal_duration_days"])
    orig_shares = list(cfg["pipeline"]["share_open_by_quarter"])
    w, dur_f = orig_w, 1.0
    solved = None
    for _round in range(12):
        probs = _pipeline_stale_probs(cfg, thr)
        target = cap * 0.88
        # early-mass budget: with the last quarter maximally fresh
        p_last = probs[-1]
        b_max = max(0.0, (target - p_last) / (1.0 - target))
        # 2% baseline everywhere: zero open mass in a quarter looks
        # broken downstream (stage history, slippage trends)
        s = [0.02] * n
        feasible = True
        for k in sorted(cov):
            # coverage_k = sum_{q<=k} s_q*n_q / (w*n_k) >= m_k
            need = cov[k] * float(o["win_rate"]) * 1.06
            have = sum(s[q] * n_q(q) / n_q(k) for q in range(k + 1))
            add = need - have
            if add > 1e-9:
                if s[k] + add > 0.95:
                    feasible = False
                    break
                s[k] += add
        early = sum(s[:n - 1])
        # Lever order matters (live s11k regression): DURATIONS gate the
        # freshest-quarter stale prob p_last - shrinking win_rate cannot
        # help that. Only shrink win_rate when coverage's early-mass
        # requirement busts the budget.
        if p_last >= target or (feasible and early <= b_max
                                and s[n - 1] < 0.95):
            pass  # durations acceptable / staleness solvable by shaping
        elif w > 0.03:
            w = max(0.02, w * 0.72)
            o["win_rate"] = round(w, 4)
            continue
        else:
            dur_f *= 0.55
            if dur_f < 0.08:
                break
            o["deal_duration_days"] = _scaled_durations(orig_dd, dur_f)
            o["win_rate"] = round(orig_w, 4)
            continue
        # top up the fresh last quarter until the blend meets target
        lo, hi = s[n - 1], 0.95

        def blend_with(sl):
            ss = s[:]
            ss[n - 1] = sl
            return sum(a * b for a, b in zip(ss, probs)) / sum(ss)

        if blend_with(hi) > target:
            # even a fully-open last quarter cannot save the blend -
            # shorten durations (fresher last quarter) and retry
            dur_f *= 0.55
            if dur_f < 0.08:
                break
            o["deal_duration_days"] = _scaled_durations(orig_dd, dur_f)
            continue
        for _ in range(40):
            mid = (lo + hi) / 2.0
            if blend_with(mid) > target:
                lo = mid
            else:
                hi = mid
        s[n - 1] = hi
        solved = s
        break

    if solved is None:
        # roll back every lever so the convergence loop starts clean
        o["win_rate"] = orig_w
        o["deal_duration_days"] = copy.deepcopy(orig_dd)
        cfg["pipeline"]["share_open_by_quarter"] = orig_shares
        fixes.append(f"{cid}: joint coverage/staleness solve found no "
                     "feasible configuration - escalating to the "
                     "convergence loop as-is")
        return
    changed = []
    new_shares = [round(v, 4) for v in solved]
    if new_shares != [float(v) for v in cfg["pipeline"]["share_open_by_quarter"]]:
        cfg["pipeline"]["share_open_by_quarter"] = new_shares
        changed.append(f"share_open={new_shares}")
    if abs(float(o["win_rate"]) - orig_w) > 1e-4:
        changed.append(f"win_rate {orig_w:.2f}->{float(o['win_rate']):.2f}")
    if abs(dur_f - 1.0) > 1e-6:
        changed.append(f"durations scaled x{dur_f:.2f}")
    if changed:
        fixes.append(f"{cid}: joint coverage/staleness solve - "
                     + ", ".join(changed))


def _autocalibrate_pipeline(cfg, criteria_doc, labels, fixes):
    """Reshape share_open_by_quarter so the predicted stale share at
    evaluation meets stage_aging caps (F25 exact model); when coverage
    criteria coexist, defer to the joint solver."""
    pipe = cfg.get("pipeline")
    if not pipe:
        return
    aging_list = [c for c in criteria_doc["criteria"]
                  if c["check"] == "stage_aging"]
    cov = _coverage_constraints(cfg, criteria_doc)
    if aging_list and cov:
        _pipeline_joint_solve(cfg, aging_list[0], cov, fixes)
        return
    if not aging_list:
        return
    c = aging_list[0]
    p = c.get("params", {})
    cap = float(p.get("max_stale_share_pct", 35)) / 100.0
    thr = float(p.get("stale_threshold_days", 120))
    shares = [float(v) for v in pipe["share_open_by_quarter"]]
    if len(shares) < 2:
        return
    probs = _pipeline_stale_probs(cfg, thr)
    new = _solve_open_shares(shares, probs, cap)
    if new is None:
        return
    pred = sum(s * f for s, f in zip(new, probs)) / sum(new)
    if pred > cap:
        # Feasibility rescue (live s11j): with durations up to ~95d
        # and a 90d staleness threshold nearly EVERY deal of any
        # quarter is stale - no share redistribution can help.
        # Duration is not measured by any check, so shorten it until
        # the cap is reachable, then re-solve the tilt.
        lo_f, hi_f = 0.15, 1.0
        best = None
        orig_dd = copy.deepcopy(
            cfg["opportunities"]["deal_duration_days"])
        for _ in range(18):
            mid = (lo_f + hi_f) / 2.0
            cfg["opportunities"]["deal_duration_days"] = \
                _scaled_durations(orig_dd, mid)
            p_m = _pipeline_stale_probs(cfg, thr)
            s_m = _solve_open_shares(shares, p_m, cap)
            b_m = sum(a * b for a, b in zip(s_m, p_m)) / sum(s_m) \
                if s_m else 0.0
            if b_m <= cap * 0.85:
                best = mid
                hi_f = mid
            else:
                lo_f = mid
        if best is None:
            cfg["opportunities"]["deal_duration_days"] = \
                _scaled_durations(orig_dd, 0.15)
        fixes.append(f"{c['id']}: shortened deal durations to "
                     f"{cfg['opportunities']['deal_duration_days']} - "
                     "the staleness cap was unreachable at the "
                     "drafted cycle length")
        probs = _pipeline_stale_probs(cfg, thr)
        new = _solve_open_shares(shares, probs, cap)
        if new is None:
            return
    pipe["share_open_by_quarter"] = new
    pred = sum(s * f for s, f in zip(new, probs)) / sum(new)
    fixes.append(f"{c['id']}: reshaped share_open_by_quarter to "
                 f"{new} -> predicted {pred * 100:.1f}% stale "
                 f"(engine-exact model, <= {cap * 100:.0f}% cap)")


def _autocalibrate_coverage(cfg, criteria_doc, fixes):
    """F25b: size quota plan levels so coverage_ratio criteria can pass.
    Coverage compares cumulative OPEN-pipeline VALUE (expected close up
    to the quarter) against that quarter's plan total; a naturally-sized
    plan leaves coverage at ~0.6x when the story wants 3x. Scale the
    plan DOWN per affected quarter to open_value/(multiple*1.12) - the
    revenue_vs_plan ratios are scale-invariant, so this cannot break
    them (attainment floats up instead)."""
    if not cfg.get("pipeline") or not cfg.get("quota"):
        return
    labels = cfg["time_model"]["quarter_labels"]
    quota = cfg["quota"]
    units_map = quota.get("by_segment") or quota.get("by_territory") or {}
    if not units_map:
        return
    n_q = len(labels)
    # expected open VALUE per created-quarter (engine model: lognormal
    # deal sizes, predicted blended discount)
    o = cfg["opportunities"]
    dl = o["deal_size_lognormal"]
    sigma = float(dl["sigma"])
    med0 = float(dl.get("median_usd", 0.0))
    medians = dl.get("medians_by_quarter")
    mults = o.get("volume_multipliers")
    disc = _predicted_discount_curve(cfg)
    shares = [float(v) for v in cfg["pipeline"]["share_open_by_quarter"]]
    v_cum, run = [], 0.0
    for qi in range(min(n_q, len(shares))):
        med = float(medians[qi]) if medians and qi < len(medians) else med0
        n_qi = o["per_quarter"] * (mults[qi] if mults else 1.0)
        run += n_qi * shares[qi] * med * (1.0 - disc[qi] / 100.0)
        v_cum.append(run)
    caps = {}
    need_default = None
    for c in criteria_doc["criteria"]:
        if c["check"] != "coverage_ratio":
            continue
        p = c.get("params", {})
        q = p.get("quarter")
        m = float(p["min_multiple"])
        need_default = m if need_default is None else min(need_default, m)
        if q not in labels:
            continue
        k = labels.index(q) + int(p.get("target_quarter_offset", 0))
        if not (0 <= k < len(v_cum)):
            continue
        caps[k] = min(caps.get(k, float("inf")), v_cum[k] / (m * 1.12))
    # Healthy-pipeline invariant: when a story cares about coverage at
    # all, no quarter's plan should exceed what open pipeline can cover
    # at ~1.25x (live s11j: the drafter drafted $18M/qtr plans that left
    # later quarters at 0.1x coverage).
    if need_default is not None:
        for k in range(len(v_cum)):
            caps[k] = min(caps.get(k, float("inf")), v_cum[k] * 0.8)
    dim = "by_segment" if quota.get("by_segment") else "by_territory"
    for k, cap_k in sorted(caps.items()):
        try:
            t_cur = sum(float(u[k]) for u in units_map.values())
        except (IndexError, TypeError, ValueError):
            continue
        if t_cur <= 0 or t_cur <= cap_k:
            continue
        f = cap_k / t_cur
        if v_cum[k] < t_cur * 0.005:
            # essentially NO open pipeline exists at that quarter - the
            # conflict is structural, not a sizing problem (live s11i:
            # an unfloored tilt zeroed open mass, then this pass scaled
            # the plan to $0 -> invalid config). Leave the plan intact;
            # the contradiction rule surfaces the conflict instead.
            fixes.append(f"coverage: Q{k + 1} has no meaningful open "
                         "pipeline to cover a plan - leaving plan "
                         "unchanged")
            continue
        for u in units_map.values():
            u[k] = round(float(u[k]) * f, 2)
        quota[dim] = units_map
        fixes.append(f"coverage: scaled plan Q{k + 1} down x{f:.2f} "
                     f"(to ${cap_k:,.0f}) so open pipeline covers it at "
                     "the required multiple")


def _autocalibrate_pass(cfg, criteria_doc, labels, dspec, eoq, boost, rw,
                        fixes, mode, tier_term, bases_sum_at):
    if mode == "tier":
        wanted = {"tier_share_shift"}
    elif mode == "levels":
        wanted = {"avg_discount_quarter", "realized_vs_list",
                  "region_discount_premium"}
    elif mode == "planning":
        return _autocalibrate_planning(cfg, criteria_doc, fixes)
    elif mode == "coverage":
        return _autocalibrate_coverage(cfg, criteria_doc, fixes)
    elif mode == "margin":
        return _autocalibrate_margin(cfg, criteria_doc, labels, fixes)
    elif mode == "pipeline":
        return _autocalibrate_pipeline(cfg, criteria_doc, labels, fixes)
    else:
        wanted = set()
    crit_list = [c for c in criteria_doc["criteria"]
                 if c["check"] in wanted]
    # region premiums first (they shift blended levels), then levels
    order = {"tier_share_shift": 0, "region_discount_premium": 1}
    share_first = sorted(crit_list, key=lambda c: order.get(c["check"], 2))
    for c in share_first:
        check, params, cid = c["check"], c.get("params", {}), c["id"]

        if check == "region_discount_premium":
            region = params.get("region")
            vs = params.get("vs") or []
            quarters = params.get("quarters") or labels
            need = float(params.get("min_premium_pp", 0)) + 1.0  # +margin
            for q in quarters:
                if q not in labels:
                    continue
                qi = labels.index(q)
                disc_r = float(dspec["base_by_quarter"].get(region, [0])[qi])
                others = [float(dspec["base_by_quarter"][o][qi])
                          for o in vs if o in dspec["base_by_quarter"]]
                if not others or region not in dspec["base_by_quarter"]:
                    continue
                worst = max(others)
                gap = disc_r - worst
                if gap < need:
                    delta = need - gap
                    dspec["base_by_quarter"][region][qi] = round(
                        disc_r + delta, 3)
                    fixes.append(f"{cid}: raised '{region}' base Q{qi + 1} "
                                 f"by {delta:+.2f}pp for >= "
                                 f"{need - 1.0:g}pp premium")

        if check == "avg_discount_quarter":
            q = params.get("quarter")
            if q not in labels:
                continue
            qi = labels.index(q)
            want = float(params["target_pct"])
            current = bases_sum_at(qi) + eoq * boost + tier_term(qi)
            delta = want - current
            if abs(delta) > 0.5:
                for vals in dspec["base_by_quarter"].values():
                    vals[qi] = round(float(vals[qi]) + delta, 3)
                fixes.append(f"{cid}: shifted all region bases Q{qi + 1} "
                             f"by {delta:+.2f}pp to hit {want:g}% avg "
                             "discount")

        elif check == "realized_vs_list":
            pairs = [("quarter_start", "target_start_pct"),
                     ("quarter_end", "target_end_pct")]
            for qkey, tkey in pairs:
                q, want = params.get(qkey), params.get(tkey)
                if q not in labels or want is None:
                    continue
                qi = labels.index(q)
                implied_disc = 100 - float(want) + 1.8
                current = bases_sum_at(qi) + eoq * boost + tier_term(qi)
                delta = implied_disc - current
                if abs(delta) > 0.5:
                    for vals in dspec["base_by_quarter"].values():
                        vals[qi] = round(float(vals[qi]) + delta, 3)
                fixes.append(f"{cid}: shifted all region bases "
                             f"Q{qi + 1} by {delta:+.2f}pp to hit "
                             f"{want:g}% realized/list")

        elif check == "discount_trend_monotonic":
            # make the BLENDED discount path monotone between its endpoint
            # values by re-deriving each quarter's base-sum from a linear
            # blend (the raw bases can be smooth while mix-shift deltas
            # warp the blended path - live s20e); skipped when a MIDDLE
            # quarter is explicitly pinned
            middle_pins = any(
                oc["check"] == "avg_discount_quarter"
                and 0 < labels.index(oc["params"].get("quarter", ""))
                < len(labels) - 1
                for oc in criteria_doc["criteria"])
            if middle_pins or len(labels) < 3:
                continue
            blended = _predicted_discount_curve(cfg)
            target = [blended[0] + (blended[-1] - blended[0]) * qi
                      / (len(labels) - 1) for qi in range(len(labels))]
            changed = False
            for qi in range(1, len(labels) - 1):
                need_base = target[qi] - eoq * boost \
                    - _quarter_tier_term(cfg, qi)
                cur_base = sum(rw[r] * float(vals[qi]) for r, vals
                               in dspec["base_by_quarter"].items())
                delta = need_base - cur_base
                if abs(delta) > 0.3:
                    for vals in dspec["base_by_quarter"].values():
                        vals[qi] = round(float(vals[qi]) + delta, 3)
                    changed = True
            if changed:
                fixes.append(f"{cid}: flattened blended discount path to "
                             "monotone interpolation between endpoints")

        elif check == "revenue_vs_plan" and not solve_levels:
            continue  # handled in the levels pass below

        elif check == "tier_share_shift" and cfg.get("products"):
            tier = params.get("tier")
            pmult = cfg["products"].get("price_multiplier_by_tier", {})
            m_t = float(pmult.get(tier, 1.0)) if tier else 0.0
            if not tier or m_t <= 0:
                continue
            for qkey, want_key in (("quarter_start", "from_share_pct"),
                                   ("quarter_end", "to_share_pct")):
                qlabel = params.get(qkey)
                if qlabel not in labels:
                    qlabel = labels[0] if qkey == "quarter_start" \
                        else labels[-1]
                want = params.get(want_key)
                if want is None:
                    continue
                qi = labels.index(qlabel)
                pred = _tier_revenue_shares_at(cfg, qi).get(tier, 0.0) * 100
                if abs(pred - float(want)) <= 2.0:
                    continue
                s = float(want) / 100.0
                # c_t * m_t / (c_t * m_t + W_o) = s
                prods_cat = cfg["products"]["catalog"]
                pm = pmult

                def cshare(p, q):
                    sv = p.get("share")
                    if isinstance(sv, dict):
                        cv = sv.get("weights_by_quarter") or [1.0]
                        return float(cv[q]) if q < len(cv) else \
                            sum(float(x) for x in cv) / len(cv)
                    return float(sv or 0.0)

                w_o = sum(cshare(p, qi) * float(pm.get(p["tier"], 1.0))
                          for p in prods_cat if p["tier"] != tier)
                c_others = sum(cshare(p, qi) for p in prods_cat
                               if p["tier"] != tier)
                # Closed form accounting for sibling rebalance: scaling the
                # tier's count share to c_t scales siblings' counts (and
                # thus their weighted mass W_o) by (1-c_t)/C_o:
                #   s = c_t*m_t / (c_t*m_t + W_o*(1-c_t)/C_o)
                # => x = B / (m_t*(1-s) + B),  B = s*W_o/C_o
                if c_others <= 0:
                    continue
                b = s * w_o / c_others
                c_t = b / (m_t * (1.0 - s) + b)
                if c_t > 0.85:
                    # infeasible by count share alone - hold count at 50%
                    # and scale the tier's own price multiplier instead:
                    #   0.5 = B / (m'(1-s) + B) => m' = B / (1-s)
                    c_t = 0.5
                    new_m = b / (1.0 - s)
                    pmult[tier] = round(new_m, 3)
                    fixes.append(f"{cid}: raised '{tier}' price multiplier "
                                 f"to {new_m:.2f} (share infeasible by "
                                 "count alone)")
                _set_count_share(cfg, tier, qi, c_t)
                fixes.append(f"{cid}: solved '{tier}' count share at "
                             f"Q{qi + 1} to {c_t:.2f} for ~{want:g}% "
                             "revenue share")


def _renormalize_product_shares_cfg(cfg):
    """Keep per-quarter product share sums at exactly 1 after edits."""
    prods = cfg.get("products")
    if not prods:
        return
    labels = cfg.get("time_model", {}).get("quarter_labels") or []
    catalog = prods.get("catalog") or []
    curves, static = [], []
    for p in catalog:
        s = p.get("share")
        if isinstance(s, dict):
            curves.append(s["weights_by_quarter"])
        elif isinstance(s, (int, float)):
            static.append(float(s))
    if not curves:
        return
    static_total = sum(static)
    for qi in range(len(labels)):
        total = sum(float(c[qi]) for c in curves) + static_total
        if total <= 0:
            continue
        k = 1.0 / total
        for c in curves:
            c[qi] = float(c[qi]) * k
