"""Capability service: turn the engine envelope into drafter TOOLS.

The acceptance gates already compute what the engine can build
(`packs/revops/envelope.py` + `criteria_lint` feasibility). This module
exposes that same math as things the DRAFTER can use at stage 2/3:

- `capability_sheet()`  - compact numeric context for the drafting prompt;
- `assess_criteria()`   - per-criterion reachability (static facts when no
                          config exists yet);
- `assess_config()`     - per-criterion predicted value, target and GAP once
                          a config is drafted (the "how far off am I?");
- `snap_criteria()`     - deterministic clamp of an unreachable target to the
                          nearest buildable value (bounded, recorded).

Closed-form checks only. Anything we cannot estimate returns
`reachable=None` and is left to the existing gates.
"""
from syngen.packs.revops import envelope


def _tax():
    from syngen.phases.intake import _pack_taxonomy
    return _pack_taxonomy()


def _sig(check):
    try:
        return (_tax()._signatures or {}).get(check) or {}
    except Exception:  # noqa: BLE001 - capability must never crash a flight
        return {}


def _num(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


def _count_shares(cfg):
    products = cfg.get("products") or {}
    catalog = products.get("catalog") or []
    mult = products.get("price_multiplier_by_tier") or {}
    shares = {}
    for e in catalog:
        t, s = e.get("tier"), e.get("share")
        if isinstance(t, str) and isinstance(s, (int, float)):
            shares[t] = shares.get(t, 0.0) + float(s)
    if not shares or not mult:
        return None, None
    total = sum(shares.values()) or 1.0
    return {t: s / total for t, s in shares.items()}, mult


def _tier_ceiling(cfg, tier):
    count_shares, mult = _count_shares(cfg)
    if not count_shares:
        return None
    return envelope.tier_share_ceiling(count_shares, mult, tier)


def capability_sheet(cfg=None):
    """Compact, NUMERIC capability context for the drafting prompt.

    Replaces the prose rulebook: what each check can actually produce, plus
    the directional signs. Small on purpose (the drafter reads ~19k chars of
    catalog; the signal must not drown)."""
    lines = ["CAPABILITY SHEET (what the engine can actually build):"]
    pinned = []
    directional = []
    scoping = []
    try:
        sigs = _tax()._signatures or {}
    except Exception:  # noqa: BLE001
        sigs = {}
    for check, sig in sigs.items():
        if sig.get("pinned_quantity"):
            pinned.append(f"- {check}: {sig['pinned_quantity']}")
        for key in ("directional_params", "pinned_quantity"):
            note = sig.get(key)
            if isinstance(note, dict):
                for pname, desc in note.items():
                    directional.append(f"- {check}.{pname}: {desc}")
        for coord in sig.get("coordinates", []):
            if coord.get("space"):
                allowed = " (or '_all_')" if coord.get("allow_all") else ""
                scoping.append(f"- {check}.{coord.get('param')}: one of the "
                               f"config's {coord['space']}{allowed}")
    lines.append("Hard limits (never exceed):")
    lines.extend(pinned or ["- (none registered)"])
    if cfg is not None:
        try:
            growth = envelope.headline_growth_ceiling(cfg)
            lines.append(f"- core_vs_headline_growth.min_headline_growth_pct: "
                         f"raking pins headline growth to ~{growth:.1f}%")
        except Exception:  # noqa: BLE001
            pass
        count_shares, mult = _count_shares(cfg)
        if count_shares:
            ceilings = {t: _tier_ceiling(cfg, t) for t in count_shares}
            pretty = ", ".join(f"{t}~{v:.0f}%" for t, v in ceilings.items()
                               if v is not None)
            if pretty:
                lines.append(f"- tier_share_shift.to_share_pct ceilings: {pretty}")
        lines.append("- effective_capacity.target_pct: reachable only <= 100 "
                     "(ramp solver)")
    lines.append("Directions:")
    lines.extend(directional[:12] or ["- (none registered)"])
    lines.append("Scoping:")
    lines.extend(scoping[:16] or ["- (none registered)"])
    return "\n".join(lines)


def _assess_one(c, cfg):
    check = c.get("check")
    p = c.get("params", {}) or {}
    sig = _sig(check)
    out = {"id": c.get("id"), "check": check, "reachable": None,
           "target": None, "predicted": None, "nearest": None,
           "param": None, "note": ""}
    pinned = sig.get("pinned_quantity")
    if pinned:
        if check == "quota_vs_potential":
            out.update(reachable=False, note=f"BLOCKED: {pinned}")
            return out
        if check == "revenue_vs_plan":
            out.update(reachable=True, note=f"PINNED: {pinned}")
            return out
        out["note"] = pinned
        return out
    if check == "effective_capacity":
        tgt = _num(p.get("target_pct"))
        out.update(param="target_pct", target=tgt)
        if tgt is not None and tgt > 100.0:
            out.update(reachable=False, predicted=100.0, nearest=100.0,
                       note="effective_capacity tops out at 100% (ramp solver)")
        else:
            out["reachable"] = True
        return out
    if check == "elasticity_differential":
        out["note"] = ("requires a pricing_response block; without it the "
                       "differential cannot be built")
        return out
    if cfg is None:
        return out
    try:
        if check == "core_vs_headline_growth":
            ceiling = envelope.headline_growth_ceiling(cfg)
            need = _num(p.get("min_headline_growth_pct"))
            out.update(param="min_headline_growth_pct", target=need,
                       predicted=ceiling,
                       nearest=(min(need, ceiling)
                                if need is not None else None),
                       reachable=(need is None or need <= ceiling + 1e-9),
                       note=f"headline growth is raking-pinned at ~{ceiling:.1f}%")
        elif check == "pipeline_concentration":
            sigma = float((cfg.get("opportunities", {})
                           .get("deal_size_lognormal", {}) or {})
                          .get("sigma", 0.6) or 0.6)
            frac = envelope.pipeline_top_share(
                cfg, sigma, int(p.get("top_n_accounts", 5)))
            out.update(param="min_top_share_pct",
                       target=_num(p.get("min_top_share_pct")),
                       predicted=None if frac is None else frac * 100.0,
                       reachable=True,
                       note="outlier multiplier is unbounded (reference only)")
        elif check == "tier_share_shift":
            ceiling = _tier_ceiling(cfg, p.get("tier"))
            need = _num(p.get("to_share_pct"))
            out.update(param="to_share_pct", target=need, predicted=ceiling,
                       nearest=(min(need, ceiling)
                                if need is not None and ceiling is not None
                                else None),
                       reachable=(need is None or ceiling is None
                                  or need <= ceiling + 1e-9),
                       note="raise the tier's price_multiplier or lower target")
        elif check == "avg_price_by_tier":
            est = envelope.avg_price_by_tier(cfg, p.get("tier"))
            cap = _num(p.get("max_avg_realized_usd"))
            out.update(param="max_avg_realized_usd", target=cap,
                       predicted=est, nearest=est,
                       reachable=(cap is None or est is None or est <= 2.0 * cap),
                       note="raise the cap or lower the plan curves")
        elif check == "win_rate_flat":
            band = _num(p.get("band_pp"))
            floor = envelope.win_rate_noise_pp(cfg)
            out.update(param="band_pp", target=band, predicted=floor,
                       nearest=(max(band, floor)
                                if band is not None and floor is not None
                                else None),
                       reachable=(band is None or floor is None
                                  or band >= floor - 1e-9),
                       note=(f"win-rate noise floor ~{floor:.1f}pp"
                             if floor is not None else ""))
    except Exception as e:  # noqa: BLE001
        out["note"] = f"capability estimate unavailable: {e}"
    return out


def assess_criteria(doc, cfg=None):
    return [_assess_one(c, cfg) for c in doc.get("criteria", [])]


def assess_config(cfg, doc):
    return assess_criteria(doc, cfg)


def snap_criteria(doc, cfg=None):
    """Deterministically clamp unreachable targets to the nearest buildable
    value. Returns (new_doc, adjustments). Bounded by construction: one pass
    over the criteria, no loop, so it can never run away."""
    findings = assess_criteria(doc, cfg)
    by_id = {c.get("id"): dict(c) for c in doc.get("criteria", [])}
    adjustments = []
    for f in findings:
        if f.get("reachable") is not False or f.get("nearest") is None \
                or not f.get("param"):
            continue
        c = by_id.get(f["id"])
        if not c:
            continue
        params = dict(c.get("params") or {})
        old = params.get(f["param"])
        params[f["param"]] = f["nearest"]
        by_id[f["id"]] = {**c, "params": params}
        adjustments.append({"id": f["id"], "param": f["param"], "from": old,
                            "to": f["nearest"], "reason": f.get("note", "")})
    new_doc = {**doc,
               "criteria": [by_id[c["id"]] for c in doc.get("criteria", [])]}
    return new_doc, adjustments
