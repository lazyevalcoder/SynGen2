"""Criteria amendment mechanics with dependency propagation (GAPS G10).

Discovered in Experiment F: amending one criterion (AC3, Q4 discount) can
silently invalidate a dependent criterion (AC7, realized_vs_list = the
complement of discount). The diff classifier proposes amendments; this module
guarantees the affected closure is surfaced before Gate 1 re-approval.

The graph walk is deterministic - no LLM involvement.
"""
import re


def apply_criterion_overrides(doc, override_text):
    """Parse 'AC3.target_pct=21; AC6.min_gap_pp=4' style overrides into the doc."""
    for chunk in (override_text or "").replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        assignment, _, value = chunk.partition("=")
        crit_id, _, param = assignment.strip().partition(".")
        value = float(value) if "." in value else int(value)
        for c in doc["criteria"]:
            if c["id"] == crit_id.strip():
                c["params"][param.strip()] = value
                break
        else:
            raise ValueError(f"unknown criterion id in override: {crit_id}")
    return doc


def dependency_closure(criteria, changed_ids):
    """All criterion IDs that must be re-reviewed when changed_ids change.

    Follows depends_on edges transitively: if AC7 depends_on AC3 and AC3
    changed, AC7 is in the closure (and so is anything depending on AC7).
    """
    dependents = {}
    for c in criteria:
        for dep in c.get("depends_on", []) or []:
            dependents.setdefault(dep, set()).add(c["id"])

    closure = set()
    frontier = list(changed_ids)
    while frontier:
        cid = frontier.pop()
        for dependent in dependents.get(cid, ()):  # noqa: B007
            if dependent not in closure and dependent not in changed_ids:
                closure.add(dependent)
                frontier.append(dependent)
    return sorted(closure)


def apply_amendments(doc, override_text):
    """Apply 'AC3.target_pct=21' style overrides; report affected dependents.

    Returns (doc, changed_ids, affected_dependents). Raises ValueError on
    malformed overrides or unknown IDs (same contract as before).
    """
    changed_ids = _changed_ids(override_text)
    doc = apply_criterion_overrides(doc, override_text)
    affected = dependency_closure(doc["criteria"], changed_ids)
    return doc, changed_ids, affected


def apply_structured_amendments(doc, amendments):
    """Apply [{'id','param','to'}] proposals from the diff classifier.

    Returns (doc, applied, errors). Unknown IDs/params land in errors and are
    surfaced to the user - never silently dropped.
    """
    by_id = {c["id"]: c for c in doc["criteria"]}
    applied, errors = [], []
    for am in amendments or []:
        cid = str(am.get("id", "")).strip()
        param = str(am.get("param", "")).strip()
        if cid not in by_id or not param:
            errors.append(am)
            continue
        by_id[cid]["params"][param] = am.get("to")
        applied.append(am)
    return doc, applied, errors


def consistency_report(doc):
    """Human-readable summary of the dependency graph for Gate 1 display."""
    edges = []
    for c in doc["criteria"]:
        deps = c.get("depends_on", []) or []
        if deps:
            edges.append(f"  {c['id']} <- depends on {', '.join(deps)}")
    return "\n".join(edges) if edges else "  (no dependencies declared)"


def _changed_ids(override_text):
    ids = []
    for chunk in re.split(r"[;,]", override_text or ""):
        chunk = chunk.strip()
        if not chunk:
            continue
        assignment = chunk.partition("=")[0]
        ids.append(assignment.strip().partition(".")[0].strip())
    return ids
