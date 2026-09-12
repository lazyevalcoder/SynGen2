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
    return out
