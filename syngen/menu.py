"""Buildable menu: the claim forms the engine can actually build (P11).

The signature registry (`packs/revops/check_signatures.json`) says what each
check needs; this module exposes that as a MENU. It is the enforcement face of
the capability work: a `blocked` check is simply not offered, so the drafter
cannot choose a path the engine cannot move.

Pure data derivation - no LLM, no config required. `menu_text()` is the compact
prompt context for the form-selection step (stage 2a).
"""


def _tax():
    from syngen.phases.intake import _pack_taxonomy
    return _pack_taxonomy()


def _sigs():
    try:
        return _tax()._signatures or {}
    except Exception:  # noqa: BLE001 - the menu must never crash a flight
        return {}


def menu_entries():
    """One entry per registered check, with its buildability metadata."""
    entries = []
    for check, sig in _sigs().items():
        entries.append({
            "check": check,
            "blocked": bool(sig.get("blocked")),
            "pinned": bool(sig.get("pinned")),
            "pinned_quantity": sig.get("pinned_quantity"),
            "coordinates": sig.get("coordinates", []),
            "directional_params": sig.get("directional_params", {}),
            "required_blocks": list(sig.get("required_blocks") or []),
        })
    return entries


def buildable_checks():
    """Every check that is not mechanically blocked."""
    return [e["check"] for e in menu_entries() if not e["blocked"]]


def blocked_checks():
    return [e["check"] for e in menu_entries() if e["blocked"]]


def is_blocked(check):
    return bool(_sigs().get(check, {}).get("blocked"))


def is_known(check):
    return check in _sigs()


def required_blocks(checks):
    """Top-level config blocks a set of checks needs (deduped)."""
    out = set()
    for c in checks or []:
        for ref in (_sigs().get(c, {}).get("required_blocks") or []):
            out.add(ref.split(".")[0])
    return out


def required_features(checks):
    """Dotted sub-key features a set of checks needs (e.g.
    `opportunities.outlier_deals`, `accounts.market_potential_usd`)."""
    out = set()
    for c in checks or []:
        for ref in (_sigs().get(c, {}).get("required_blocks") or []):
            if "." in ref:
                out.add(ref)
    return out


def _vocab(check):
    try:
        for cell in _tax()._cells.values():
            if check in cell.get("checks", []) and cell.get("vocab"):
                return cell["vocab"]
    except Exception:  # noqa: BLE001
        pass
    return ""


def buildable_check_names(sep=" | "):
    """Registered check names with the blocked ones removed (P13)."""
    return sep.join(e["check"] for e in menu_entries() if not e["blocked"])


def buildable_catalog():
    """The generated check catalog minus blocked checks (P13).

    Every drafting/repair path that uses this can no longer even name a
    blocked check - the enforcement gap seen in scenario 15."""
    lines = []
    for e in menu_entries():
        if e["blocked"]:
            continue
        vocab = _vocab(e["check"])
        lines.append(f"- {e['check']}: {vocab}" if vocab else f"- {e['check']}")
    return "\n".join(lines)


def _params_key(c):
    import json
    return json.dumps(c.get("params", {}) or {}, sort_keys=True)


def _coord_key(c):
    sig = _sigs().get(c.get("check"), {})
    params = c.get("params", {}) or {}
    parts = []
    for coord in sig.get("coordinates", []):
        pname = coord.get("param")
        parts.append((pname, str(params.get(pname))))
    return tuple(sorted(parts))


def menu_findings(doc):
    """Hard findings for criteria that violate the buildable menu (P13).

    Catches: unknown checks, blocked checks (the engine cannot move the
    quantity), and exact duplicate criteria. Deterministic - no LLM."""
    findings = []
    seen = {}
    for c in doc.get("criteria", []):
        cid = c.get("id")
        check = c.get("check")
        if not is_known(check):
            findings.append(
                f"{cid}: check '{check}' is not a registered engine check - "
                "re-express the claim with a buildable check.")
            continue
        if is_blocked(check):
            findings.append(
                f"{cid}: check '{check}' is BLOCKED (the engine cannot move "
                "this quantity) - re-express the SAME claim with a buildable "
                "check.")
        key = (check, _coord_key(c), _params_key(c), c.get("source_claim"))
        if key in seen:
            findings.append(f"{cid}: exact duplicate of {seen[key]} - merge "
                            "them into one criterion.")
        else:
            seen[key] = cid
    return findings


def engine_limits_for(checks):
    """Pinned-quantity / blocked notes for a SUBSET of checks (P13), so the
    number-filling step sees the engine's hard limits for the checks it is
    actually allowed to use."""
    lines = []
    for check in sorted(set(checks or [])):
        sig = _sigs().get(check, {})
        if sig.get("pinned_quantity"):
            lines.append(f"- {check}: {sig['pinned_quantity']}")
        if sig.get("blocked"):
            lines.append(f"- {check}: BLOCKED - do not use.")
    return "\n".join(lines)



def menu_text(include_blocked=True):
    """Compact prompt context: the buildable forms, their config needs, and
    the directional signs that invert a claim when wrong."""
    lines = ["BUILDABLE CHECKS (choose exactly one per claim):"]
    for e in menu_entries():
        if e["blocked"] and not include_blocked:
            continue
        mark = (" [BLOCKED - the engine cannot build this; do NOT choose it]"
                if e["blocked"] else "")
        blocks = ", ".join(e["required_blocks"]) or "none"
        vocab = _vocab(e["check"])
        desc = f": {vocab}" if vocab else ""
        lines.append(f"- {e['check']}{mark}{desc} (config needs: {blocks})")
    directions = []
    for e in menu_entries():
        for pname, desc in (e["directional_params"] or {}).items():
            directions.append(f"- {e['check']}.{pname}: {desc}")
    if directions:
        lines.append("")
        lines.append("DIRECTIONAL SIGNS (get these wrong and the claim inverts):")
        lines.extend(directions)
    limits = [(e["check"], e["pinned_quantity"]) for e in menu_entries()
              if e["pinned_quantity"]]
    if limits:
        lines.append("")
        lines.append("ENGINE LIMITS:")
        for check, note in limits:
            lines.append(f"- {check}: {note}")
    return "\n".join(lines)
