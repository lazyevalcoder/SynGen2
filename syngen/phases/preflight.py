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
    for mode in ("tier", "tier", "levels", "planning", "margin", "pipeline"):
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


def _autocalibrate_pipeline(cfg, criteria_doc, labels, fixes):
    """Reshape share_open_by_quarter so the stale share at evaluation
    (last quarter end) meets stage_aging caps: shift open-pipeline mass
    toward later quarters (live s11: 80% stale because early quarters
    held most of the open mass)."""
    pipe = cfg.get("pipeline")
    if not pipe:
        return
    for c in criteria_doc["criteria"]:
        if c["check"] != "stage_aging":
            continue
        p = c.get("params", {})
        cap = float(p.get("max_stale_share_pct", 35)) / 100.0
        thr = float(p.get("stale_threshold_days", 120))
        shares = [float(v) for v in pipe["share_open_by_quarter"]]
        n = len(shares)
        if n < 2:
            continue
        q_len = 91.33
        # Exact age bounds: created spans [q_start - dmax, q_end - dmin],
        # so ages at evaluation span [q_end_age + dmin, q_start_age + dmax]
        # (live s11g fix: 'created = close - duration' reaches BEFORE the
        # deal's own quarter - the quarter-end approximation underpredicted
        # staleness by ~50pp).
        o = cfg["opportunities"]
        dd = o["deal_duration_days"]
        if isinstance(dd, dict):
            spread = float(dd.get("spread", 10))
            mean_d = float(np.mean(dd.get("means", [30])))
            dmin, dmax = max(0.0, mean_d - spread), mean_d + spread
        else:
            dmin, dmax = float(dd[0]), float(dd[1])
        stale_fracs = []
        for qi in range(n):
            q_end_age = (n - 1 - qi) * q_len
            age_lo = q_end_age + dmin
            age_hi = q_end_age + q_len + dmax
            if age_hi <= thr:
                stale_fracs.append(0.0)
            elif age_lo >= thr:
                stale_fracs.append(1.0)
            else:
                stale_fracs.append(min(1.0, max(0.0,
                    (age_hi - thr) / max(1e-9, age_hi - age_lo))))
        stale_flags = [f > 0.99 for f in stale_fracs]

        # Closed form generalized: expected stale share =
        # Σ s_q · frac_q / Σ s_q. Solve for stale-block mass when all
        # stale-flagged quarters are ~fully stale; otherwise scale their
        # shares down proportionally until the blend meets target.
        fresh_idx = [qi for qi in range(n) if stale_fracs[qi] < 0.99]
        stale_idx = [qi for qi in range(n) if stale_fracs[qi] >= 0.99]
        cur = list(shares)
        if not fresh_idx or not stale_idx:
            # partial-staleness everywhere: shrink stale-heavy quarters by
            # a common factor until predicted share <= target
            for _ in range(60):
                pred = sum(s * f for s, f in zip(cur, stale_fracs)) / \
                    max(1e-9, sum(cur))
                if pred <= cap * 0.6:
                    break
                for qi in range(n):
                    if stale_fracs[qi] > 0.5:
                        cur[qi] *= 0.85
                    else:
                        cur[qi] *= 1.06
            new = [round(v, 4) for v in cur]
        else:
            target = cap * 0.6
            stale_orig = sum(cur[qi] for qi in stale_idx)
            new = list(cur)
            if stale_orig > 1e-9:
                k = target / stale_orig
                for qi in stale_idx:
                    new[qi] = min(0.9, cur[qi] * k)
                blk = sum(new[qi] for qi in stale_idx)
                if blk > 0:
                    for qi in stale_idx:
                        new[qi] *= target / blk
            rem = 1.0 - sum(new[qi] for qi in stale_idx)
            even_f = min(0.9, rem / len(fresh_idx))
            for qi in fresh_idx:
                new[qi] = even_f
            tot = sum(new)
            new = [round(v / tot, 4) for v in new]
        if new != shares:
            pipe["share_open_by_quarter"] = new
            fixes.append(f"{c['id']}: reshaped share_open_by_quarter to "
                         f"{new} for <= {cap * 100:.0f}% stale share "
                         f"(durations {dmin:.0f}-{dmax:.0f}d accounted)")


def _autocalibrate_pass(cfg, criteria_doc, labels, dspec, eoq, boost, rw,
                        fixes, mode, tier_term, bases_sum_at):
    if mode == "tier":
        wanted = {"tier_share_shift"}
    elif mode == "levels":
        wanted = {"avg_discount_quarter", "realized_vs_list",
                  "region_discount_premium"}
    elif mode == "planning":
        return _autocalibrate_planning(cfg, criteria_doc, fixes)
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
