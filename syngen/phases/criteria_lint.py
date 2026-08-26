"""P5 flight-control envelope: coordinate linting for criteria.

Two deterministic gates derived from the pack's check-signature registry:

- lint_criteria_internal: config-independent consistency (Gate 1). Two
  criteria addressing the SAME coordinate of the same check must have
  overlapping target bands - otherwise the set is provably unsatisfiable
  regardless of knobs (cert finding F15.2/F18.2).
- cross_lint: criteria x config geometry (post-calibration, pre-loop).
  Every coordinate criterion must address units that exist in the drafted
  config's legal unit spaces (F11.1/F11.2/F18.3 pseudo-units and
  cross-block mismatches die here instead of after generating data).

Every rule is general algebra over the signature registry - no
story-specific cases.
"""
import json

from syngen.packs.loader import load_pack

_TARGET_FIELDS = {
    # check -> (target field, tolerance field)
    "revenue_vs_plan": ("target_pct", "band_pct"),
    "avg_discount_quarter": ("target_pct", "tolerance_pp"),
    "effective_capacity": ("target_pct", "band_pp"),
    "quota_vs_potential": ("target_ratio_pct", "band_pp"),
    "forecast_vs_actual": ("target_pct", "band_pp"),
    "creation_volume_trend": ("target_decline_pct", "tolerance_pp"),
    "deal_size_trend": ("target_change_pct", "tolerance_pp"),
    "blended_margin_trend": ("target_change_pct", "tolerance_pp"),
}

_PACK_CACHE = {}


def _pack():
    if "pack" not in _PACK_CACHE:
        _PACK_CACHE["pack"] = load_pack()
    return _PACK_CACHE["pack"]


def reset_cache():
    _PACK_CACHE.clear()


def _coordinates(criterion):
    """Resolved coordinate tuple for a criterion, per the registry."""
    sigs = _pack().check_signatures.get("signatures", {})
    sig = sigs.get(criterion["check"])
    if not sig:
        return (("__unregistered__", criterion["check"]),)
    params = criterion.get("params", {})
    parts = []
    for coord in sig.get("coordinates", []):
        pname = coord.get("param")
        if coord.get("space") is None:
            # dimension selector: part of the identity
            parts.append((pname, str(params.get(pname))))
            continue
        via = coord.get("via_dimension")
        dim = str(params.get(via)) if via else \
            str(coord.get("default_dimension"))
        value = params.get(pname)
        allow_all = bool(coord.get("allow_all"))
        if value is None and not allow_all:
            value = "__unscoped__"
        parts.append((f"{dim}:{pname}", str(value)))
    return tuple(sorted(parts))


def _target_band(criterion):
    fields = _TARGET_FIELDS.get(criterion["check"])
    if not fields:
        return None
    p = criterion.get("params", {})
    target = p.get(fields[0])
    if target is None:
        return None
    return float(target), float(p.get(fields[1], 0.0))


def lint_criteria_internal(criteria_doc):
    """Config-independent consistency findings (Gate 1, WP2).

    Returns (hard_findings, notes); hard = provably unsatisfiable sets,
    notes = unscoped-coordinate advisories.
    """
    groups = {}
    notes = []
    hard = []
    known = set(_pack().checks)
    for c in criteria_doc.get("criteria", []):
        if c["check"] not in known:
            hard.append(
                f"{c['id']}: check '{c['check']}' is not in the pack's "
                "check registry - no validator or solver can evaluate it. "
                "Re-express the claim with a real check or classify it as "
                "a vocabulary gap.")
            continue
        sigs = _pack().check_signatures.get("signatures", {})
        sig = sigs.get(c["check"])
        if sig:
            for coord in sig.get("coordinates", []):
                if coord.get("space") and coord.get("required") and \
                        c.get("params", {}).get(coord["param"]) is None and \
                        not coord.get("allow_all"):
                    notes.append(
                        f"{c['id']}: {c['check']} does not scope "
                        f"'{coord['param']}' - it will be interpreted per "
                        "the config's plan geometry; scope it explicitly "
                        "if the claim targets one unit")
        band = _target_band(c)
        if band is None:
            continue
        key = (c["check"], _coordinates(c),
               bool(c.get("params", {}).get("exclude_outlier_deals")))
        groups.setdefault(key, []).append((c, band))
    for (check, coords, _), members in sorted(
            groups.items(), key=lambda kv: str(kv[0])):
        if len(members) < 2:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                (ca, (t1, tol1)), (cb, (t2, tol2)) = members[i], members[j]
                if abs(t1 - t2) > tol1 + tol2:
                    hard.append(
                        f"{ca['id']} and {cb['id']} pin {check} at "
                        f"{t1:g}+/-{tol1:g} and {t2:g}+/-{tol2:g} on the "
                        f"same coordinate {dict(coords)} - non-overlapping "
                        "bands are jointly unsatisfiable")
    return hard, notes


def unit_spaces(cfg):
    """Legal coordinate values resolvable from a drafted config."""
    labels = cfg["time_model"]["quarter_labels"]
    spaces = {"quarters": set(labels)}
    acc = cfg.get("accounts") or {}

    def _keys(block):
        return set(block.keys()) if isinstance(block, dict) else set()

    spaces["regions"] = _keys(acc.get("regions"))
    spaces["segments"] = _keys(acc.get("segments"))
    terr = acc.get("territories")
    spaces["territories"] = _keys(terr if isinstance(terr, dict) else {})
    quota = cfg.get("quota") or {}
    qunits = set()
    for sub in ("by_segment", "by_territory", "by_motion"):
        qunits |= _keys(quota.get(sub))
    spaces["quota_units"] = qunits
    cap = cfg.get("capacity") or {}
    cunits = set()
    for sub in ("by_region", "by_territory"):
        cunits |= _keys(cap.get(sub))
    spaces["capacity_units"] = cunits
    products = cfg.get("products") or {}
    catalog = products.get("catalog")
    tiers = set()
    if isinstance(catalog, list):
        tiers = {str(e.get("tier")) for e in catalog
                 if isinstance(e, dict) and e.get("tier")}
    spaces["tiers"] = tiers
    return spaces


def cross_lint(cfg, criteria_doc):
    """Criteria x config geometry findings (WP3).

    Runs AFTER calibration/synthesis so synthesized blocks count. Returns
    HARD findings; empty = every coordinate lands inside the model.
    """
    spaces = unit_spaces(cfg)
    sigs = _pack().check_signatures.get("signatures", {})
    findings = []
    for c in criteria_doc.get("criteria", []):
        sig = sigs.get(c["check"])
        if sig is None:
            continue
        params = c.get("params", {})
        for coord in sig.get("coordinates", []):
            space_name = coord.get("space")
            if space_name is None:
                continue
            value = params.get(coord["param"])
            if value is None:
                if coord.get("required") and spaces.get(space_name):
                    findings.append(
                        f"{c['id']}: {c['check']} requires "
                        f"'{coord['param']}' but none was drafted "
                        f"(legal {space_name}: "
                        f"{sorted(spaces[space_name])[:8]})")
                continue
            if bool(coord.get("allow_all")) and str(value) == "_all_":
                continue
            space = spaces.get(space_name, set())
            if not space:
                continue
            values = value if isinstance(value, list) and \
                coord.get("multi") else [value]
            for v in values:
                if str(v) not in space:
                    findings.append(
                        f"{c['id']}: {c['check']} '{coord['param']}'="
                        f"'{v}' is outside the data model (legal "
                        f"{space_name}: {sorted(space)[:8]})")
    findings.extend(_feasibility_findings(cfg, criteria_doc))
    return findings


def _feasibility_findings(cfg, criteria_doc):
    """P5 WP6 (F13.2): economic infeasibility of price caps under raking.

    With a quota block, closed-won revenue is RAKED to plan x attainment,
    so a tier's average realized price ~= plan_total / won_count scaled by
    the tier's relative price position - NOT by list-price knobs. A cap far
    below that floor is unreachable no matter how the proposer turns price
    knobs (cert scenario_03 burned its whole budget proving this).
    Conservative: flagged only at 2x the estimated floor.
    """
    quota = cfg.get("quota")
    products = cfg.get("products") or {}
    catalog = products.get("catalog")
    opps = cfg["opportunities"]
    if not quota or not isinstance(catalog, list) or not catalog:
        return []
    labels = cfg["time_model"]["quarter_labels"]
    qi = len(labels) - 1

    by_seg = quota.get("by_segment")
    dim_name = "segment"
    if not isinstance(by_seg, dict):
        for sub, dn in (("by_territory", "territory"),
                        ("by_motion", "motion")):
            if isinstance(quota.get(sub), dict):
                by_seg, dim_name = quota[sub], dn
                break
    if not isinstance(by_seg, dict):
        return []

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
        return []
    if won_n <= 0:
        return []
    avg_deal = attained / won_n if attained else plan_total / won_n

    mult = products.get("price_multiplier_by_tier") or {}
    shares = {}
    for e in catalog:
        t = e.get("tier")
        s = e.get("share")
        if isinstance(t, str) and isinstance(s, (int, float)):
            shares[t] = shares.get(t, 0.0) + float(s)
    if not shares or not mult:
        return []
    total_count_share = sum(shares.values()) or 1.0
    count_shares = {t: s / total_count_share for t, s in shares.items()}
    denom = sum(count_shares.get(t, 0.0) * float(mult.get(t, 1.0))
                for t in count_shares)
    if denom <= 0:
        return []

    findings = []
    for c in criteria_doc.get("criteria", []):
        if c["check"] != "avg_price_by_tier":
            continue
        p = c.get("params", {})
        cap = p.get("max_avg_realized_usd")
        tier = p.get("tier")
        if cap is None or tier not in count_shares:
            continue
        est = avg_deal * float(mult.get(tier, 1.0)) / denom
        if est > 2.0 * float(cap):
            findings.append(
                f"{c['id']}: avg realized price cap ${float(cap):,.0f} for "
                f"tier '{tier}' is economically unreachable under raking - "
                f"the drafted plan implies ~${est:,.0f} average for this "
                "tier (plan totals are plan-of-record). Lower the plan "
                "curves, raise the cap, or raise this tier's volume share.")
    findings.extend(_tier_share_feasibility(cfg, criteria_doc, mult, shares))
    return findings


def _tier_share_feasibility(cfg, criteria_doc, mult, count_shares):
    """P6 P1.4 (cert s12 F19.3): tier revenue-share reachability.

    Revenue share of a tier ~= count_share * price_mult / sum(count_share_i
    * price_mult_i). A target share therefore caps the COUNT share the tier
    can absorb; when the target exceeds the ceiling even with ALL remaining
    count share allocated to the tier, the criterion is arithmetically
    unlandable no matter how the proposer turns knobs. Conservative: the
    model assumes list prices (engine realized prices run at or below list),
    so a flag here is a true ceiling, never a false kill.
    """
    if not mult or not count_shares:
        return []
    tiers = list(count_shares)
    if len(tiers) < 2:
        return []
    floor = 0.05  # other tiers must retain a residual presence
    findings = []
    for c in criteria_doc.get("criteria", []):
        if c["check"] != "tier_share_shift":
            continue
        p = c.get("params", {})
        tier = p.get("tier")
        target = p.get("to_share_pct")
        if tier not in count_shares or target is None:
            continue
        others = [t for t in tiers if t != tier]
        count_c = max(0.0, 1.0 - floor * len(others))
        denom = count_c * float(mult.get(tier, 1.0)) + \
            sum(floor * float(mult.get(t, 1.0)) for t in others)
        ceiling = count_c * float(mult.get(tier, 1.0)) / denom * 100.0
        if float(target) > ceiling + 1e-9:
            findings.append(
                f"{c['id']}: tier_share_shift target {float(target):g}% "
                f"revenue share for tier '{tier}' is arithmetically "
                f"unreachable - even with all remaining count share it tops "
                f"out near {ceiling:.0f}% at the drafted price multiplier "
                f"({mult.get(tier)}). Raise this tier's price_multiplier or "
                "lower the target.")
    return findings


def render_lint(findings):
    return "\n".join(f"  - {f}" for f in findings)


def corrective_brief(findings):
    """Compact text for a corrective re-draft prompt."""
    return ("CRITERION CONSISTENCY VIOLATIONS - fix ALL of these:\n"
            + "\n".join(f"- {f}" for f in findings))


def _dump(obj):
    return json.dumps(obj, indent=2)
