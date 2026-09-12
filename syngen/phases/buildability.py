"""Stage-3 buildability gate (P13).

A simulator config can be schema-valid and still be unable to express its
own criteria: a required optional block (products/pipeline/quota/capacity/
ownership/activity/forecast/pricing_response) or a sub-key feature
(`accounts.market_potential_usd`, `opportunities.outlier_deals`) is missing,
so the check fails structurally in the loop. Scenario 16 shipped exactly
that: `elasticity_differential` with no `pricing_response`.

This gate is deterministic and runs at the end of stage 3, before the stage
may be called complete.
"""
from syngen.menu import required_blocks, required_features


class BuildabilityError(ValueError):
    """The assembled config cannot express one or more criteria."""


def verify_config(cfg, checks):
    """Return hard findings: required blocks/features missing from cfg."""
    findings = []
    for block in sorted(required_blocks(checks)):
        if not cfg.get(block):
            findings.append(
                f"missing required block '{block}' (needed by the criteria's "
                "checks)")
    for feat in sorted(required_features(checks)):
        top, _, sub = feat.partition(".")
        node = cfg.get(top) if isinstance(cfg.get(top), dict) else {}
        if sub and not node.get(sub):
            findings.append(
                f"missing required feature '{feat}' (needed by the criteria's "
                "checks)")
    return findings


def missing_blocks(findings):
    """Top-level block names named by verify_config findings."""
    out = []
    for m in findings:
        if "missing required block '" in m:
            out.append(m.split("'")[1])
        elif "missing required feature '" in m:
            out.append(m.split("'")[1].split(".")[0])
        elif "block '" in m:
            out.append(m.split("block '", 1)[1].split("'", 1)[0])
    return out


def cross_block_findings(cfg):
    """P16: block unit names must exist in the core's dimensions.

    `quota.by_territory` keys must be `accounts.territories`;
    `by_segment` -> `accounts.segments`; `capacity` units likewise. Catches
    the scenario-15 mismatch where the quota block invented territory names
    the core never defined (both local and DeepSeek failed on it)."""
    findings = []
    acc = cfg.get("accounts") or {}
    dims = {
        "territory": set((acc.get("territories") or {}).keys()),
        "segment": set((acc.get("segments") or {}).keys()),
        "region": set((acc.get("regions") or {}).keys()),
    }
    quota = cfg.get("quota") or {}
    for dim, key in (("by_territory", "territory"),
                     ("by_segment", "segment"),
                     ("by_region", "region")):
        units = quota.get(dim)
        if not isinstance(units, dict) or not units:
            continue
        known = dims.get(key, set())
        if not known:
            continue
        bad = [u for u in units if u not in known]
        if bad:
            findings.append(
                f"block 'quota' references unknown {key} units {sorted(bad)}; "
                f"use exactly: {sorted(known)}")
    units = quota.get("by_motion")
    if isinstance(units, dict) and units:
        known = {"New Logo", "Expansion"}
        bad = [u for u in units if u not in known]
        if bad:
            findings.append(
                f"block 'quota' references unknown motion units {sorted(bad)}; "
                f"use exactly: {sorted(known)}")
    # P17: attainment maps must key on the SAME units as the chosen quota
    # dimension (scenario 15: attainment['Enterprise'] with by_territory).
    chosen = None
    for dim in ("by_segment", "by_territory", "by_motion"):
        if isinstance(quota.get(dim), dict) and quota[dim]:
            chosen = dim
            break
    if chosen:
        chosen_units = set(quota[chosen])
        for att_key in ("attainment", "attainment_by_segment",
                        "attainment_ex_outliers"):
            att = quota.get(att_key)
            if not isinstance(att, dict) or not att:
                continue
            bad = [u for u in att if u not in chosen_units]
            if bad:
                findings.append(
                    f"block 'quota' has {att_key} keys {sorted(bad)} that do "
                    f"not match its {chosen} units {sorted(chosen_units)}")
    cap = cfg.get("capacity") or {}
    for dim, key in (("by_territory", "territory"), ("by_region", "region")):
        units = cap.get(dim)
        if not isinstance(units, dict) or not units:
            continue
        known = dims.get(key, set())
        if not known:
            continue
        bad = [u for u in units if u not in known]
        if bad:
            findings.append(
                f"block 'capacity' references unknown {key} units "
                f"{sorted(bad)}; use exactly: {sorted(known)}")
    return findings
