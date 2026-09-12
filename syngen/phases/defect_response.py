"""Defect-Response rework (experiment).

Framework borrowed from ITIL incident/problem management and aviation CRM:

- role separation: detector (gates) -> diagnoser (judge) -> resolver
  (runbook/fixer) -> verifier (deterministic guards);
- a MINIMAL work order as the handoff, instead of the full drafter prompt;
- a known-error runbook for recurring mechanical classes (no LLM);
- targeted change control (a patch, not a rewrite);
- closed-loop verification (the patch must survive the guards).

Why: the classic rework hands the drafter the entire prompt (story + ~7.5k
check catalog + ~5.5k guide); the judge's prose feedback is ~2% of it. Here
the resolver sees only the target criterion, its source claim, the facts for
its check, and the diagnosis.
"""
import json

from syngen.phases.criteria_lint import lint_criteria_internal
from syngen.phases.json_task import chat_json
from syngen.prompts import load_prompt

# Known-error runbook: mechanical range-bounding for one-sided checks.
# (check) -> (floor_param, ceil_param, ceiling sizing)
_RANGE_BOUNDS = {
    "coverage_ratio": ("min_multiple", "max_multiple", "ratio"),
    "pipeline_concentration": ("min_top_share_pct", "max_top_share_pct", "pp20"),
    "revenue_concentration": ("min_top_share_pct", "max_top_share_pct", "pp20"),
    "slippage_trend": ("min_increase_pp", "max_increase_pp", "x2"),
}


def _taxonomy():
    from syngen.phases.intake import _pack_taxonomy
    return _pack_taxonomy()


def classify_defect(verdict, evidence):
    """Heuristic defect class from the judge's verdict + escalation evidence."""
    text = " ".join(str(x) for x in (
        evidence.get("reason"), evidence.get("detail"),
        verdict.get("reason"), verdict.get("guidance")) if x).lower()
    if evidence.get("kind") == "draft_invalid":
        if "known" in text or "key" in text:
            return "schema_key_mismatch"
        return "missing_surface"
    if "blocked" in text or "cannot move" in text or "pinned" in text \
            or "raking" in text:
        return "blocked_path"
    if "one-sided" in text or "overshoot" in text or "vacuous" in text:
        return "one_sided"
    if "does not exist" in text or "pseudo" in text or "not a known" in text \
            or "unknown" in text:
        return "pseudo_unit"
    if "ceiling" in text or "unreachable" in text or "above" in text:
        return "above_ceiling"
    return "unreachable"


def build_work_order(verdict, evidence, doc, taxonomy=None):
    """Concise, structured handoff for the resolver (runbook/fixer)."""
    crit = {c.get("id"): c for c in doc.get("criteria", [])}
    targets = [s for s in (verdict.get("scope") or []) if s in crit]
    if not targets:
        targets = list(crit)
    checks = {crit[t].get("check") for t in targets if t in crit}
    tax = taxonomy if taxonomy is not None else _taxonomy()
    order = {
        "defect_class": classify_defect(verdict, evidence),
        "artifact": "criteria",
        "targets": targets,
        "existing_ids": list(crit),
        "observed": {
            t: {"check": crit[t].get("check"),
                "params": crit[t].get("params", {}),
                "source_claim": crit[t].get("source_claim", "")}
            for t in targets if t in crit
        },
        "root_cause": verdict.get("reason") or evidence.get("reason") or "",
        "fix_intent": verdict.get("guidance") or "",
    }
    if tax is not None:
        facts = tax.check_facts(checks)
        if facts:
            order["allowed"] = facts
        # the fixer may need to SWITCH checks for a blocked path; give it the
        # registered names (small) so it can pick a reachable one.
        order["checks_available"] = tax.check_names(sep=", ")
    return order


def runbook_fix(work_order, doc):
    """Deterministic known-error fix: bound any one-sided target whose check
    supports a ceiling. Returns a patch list, or None if nothing applies."""
    crit = {c.get("id"): c for c in doc.get("criteria", [])}
    patch = []
    for tid in work_order.get("targets", []):
        c = crit.get(tid)
        if not c:
            continue
        rule = _RANGE_BOUNDS.get(c.get("check"))
        if not rule:
            continue
        floor_p, ceil_p, sizing = rule
        params = dict(c.get("params") or {})
        floor = params.get(floor_p)
        if not isinstance(floor, (int, float)) or isinstance(floor, bool) \
                or ceil_p in params:
            continue
        if sizing == "x2":
            ceiling = floor * 2
        elif sizing == "ratio":
            ceiling = round(floor * 1.5, 2)
        elif sizing == "pp20":
            ceiling = min(100.0, floor + 20.0)
        else:
            continue
        params[ceil_p] = ceiling
        patch.append({**c, "params": params})
    return patch or None


def fixer_patch(client, work_order, log_fn=print):
    """One minimal-context LLM call -> a targeted criteria patch."""
    system = load_prompt("fixer",
                         work_order=json.dumps(work_order, indent=2))
    try:
        result = chat_json(client, "fixer", system, "Produce the patch now.")
    except Exception as e:  # noqa: BLE001 - fixer must fail open to escalate
        log_fn(f"Fixer failed ({e}) - escalating.")
        return None
    patch = result.get("patch")
    if not isinstance(patch, list) or not patch:
        return None
    return patch


def verify_patch(patch, doc, targets):
    """Apply a patch to a COPY and verify it is claim-preserving and sound.

    Allowed: modify a target in place, or SPLIT a target into new criteria
    (fresh ids). Forbidden: touching an existing non-target criterion, or
    introducing a claim that is not one of the targets' source claims.
    Returns (new_doc, ok, reason)."""
    crit = {c.get("id"): dict(c) for c in doc.get("criteria", [])}
    existing = set(crit)
    target_claims = {crit[t].get("source_claim") for t in targets if t in crit}
    added = []
    for item in patch:
        if not isinstance(item, dict):
            return doc, False, "patch item is not an object"
        tid = item.get("id")
        if not item.get("check"):
            return doc, False, f"patch missing check for {tid!r}"
        if tid in existing and tid not in targets:
            return doc, False, f"patch touched non-target {tid!r}"
        if item.get("source_claim") not in target_claims:
            return doc, False, (f"patch item {tid!r} does not preserve a "
                                "target source_claim")
        if tid in crit:
            merged = dict(crit[tid])
            for key in ("name", "check", "params", "classification",
                        "depends_on"):
                if key in item:
                    merged[key] = item[key]
            crit[tid] = merged
        else:
            crit[tid] = {"id": tid, "name": item.get("name", tid),
                         "check": item["check"],
                         "params": item.get("params", {}),
                         "classification": item.get("classification",
                                                    "parametric"),
                         "source_claim": item["source_claim"],
                         "depends_on": item.get("depends_on", [])}
            added.append(tid)
    new_doc = {**doc,
               "criteria": [crit[c["id"]] for c in doc.get("criteria", [])]
               + [crit[a] for a in added]}
    hard, _ = lint_criteria_internal(new_doc)
    if hard:
        return new_doc, False, ("patched criteria still inconsistent: "
                                + "; ".join(str(h) for h in hard[:2]))
    return new_doc, True, ""


def defect_response(client, verdict, evidence, doc, log_fn=print,
                    taxonomy=None):
    """Triage -> runbook -> fixer -> verify.

    Returns (new_doc, ok, directive). Only handles `rework_criteria`; other
    actions are reported so the caller can fall back to the classic path.
    """
    order = build_work_order(verdict, evidence, doc, taxonomy=taxonomy)
    directive = {"defect_class": order["defect_class"],
                 "targets": order["targets"], "resolver": None,
                 "reason": ""}
    if verdict.get("action") != "rework_criteria":
        directive["resolver"] = "skip"
        directive["reason"] = "not a criteria defect"
        return doc, False, directive

    resolver = "runbook"
    patch = runbook_fix(order, doc)
    if patch is None:
        resolver = "fixer"
        patch = fixer_patch(client, order, log_fn=log_fn)
    directive["resolver"] = resolver
    if patch is None:
        directive["reason"] = "no patch produced"
        return doc, False, directive

    new_doc, ok, why = verify_patch(patch, doc, set(order["targets"]))
    directive["reason"] = why or f"{resolver} patch verified"
    return new_doc, ok, directive
