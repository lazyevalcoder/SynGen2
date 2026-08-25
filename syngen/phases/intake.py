"""Phase 1: story pre-check and decomposition into acceptance criteria.

The coverage guard (M5 iter 5, R6) lives here too: it refuses to let a
session proceed on criteria that express none of the story's computable
claims - the vacuous-convergence hole where #24 "landed" 0/0 and #9/#13
landed on generic hygiene checks alone.
"""
import json
from pathlib import Path

from syngen.config import validate_criteria_doc
from syngen.phases.json_task import chat_json
from syngen.prompts import load_prompt
from syngen.validator.checks import CHECKS

# Hygiene checks that pass on almost any well-formed dataset; they can
# accompany real criteria but must never be the ONLY expression of a
# story with computable claims.
GENERIC_CHECKS = {"data_sanity"}

MAX_COVERAGE_REDRAFTS = 1


def precheck_claims(client, story, log_fn=print):
    system = load_prompt("precheck")
    claims = chat_json(client, "precheck", system, story)
    log_fn(f"Pre-check found {len(claims.get('claims', []))} claims; "
           f"{len(claims.get('questions_for_user', []))} question(s) for user")
    return claims


def deterministic_gaps(doc, computable_claims):
    """No-LLM coverage rules. Cheap, exact, always on."""
    criteria = doc.get("criteria", [])
    if not criteria:
        return ["No criteria were drafted at all - nothing would be verified."]
    non_generic = [c for c in criteria if c["check"] not in GENERIC_CHECKS]
    if computable_claims and not non_generic:
        return [
            "Every drafted criterion is generic hygiene ("
            + ", ".join(sorted({c['check'] for c in criteria}))
            + "); none expresses the story's computable claims: "
            + "; ".join(f"'{c}'" for c in computable_claims)]
    return []


def audit_coverage(client, story, doc, computable_claims, log_fn=print):
    """LLM audit: does any criterion actually test each computable claim?

    Fails OPEN: if the audit call itself fails (endpoint down, unparseable
    output), the deterministic rules remain the active guard rather than
    blocking every session on auditor availability.
    """
    if not computable_claims:
        return []
    crit_lines = "\n".join(
        f"- {c['id']} check={c['check']} params={json.dumps(c['params'])} "
        f"(claim: {c.get('source_claim', 'n/a')})"
        for c in doc["criteria"])
    user = (f"STORY:\n{story}\n\nCOMPUTABLE CLAIMS:\n"
            + "\n".join(f"- {c}" for c in computable_claims)
            + f"\n\nCRITERIA:\n{crit_lines}")
    try:
        result = chat_json(client, "coverage_audit",
                           load_prompt("coverage_audit",
                                       checks=", ".join(sorted(CHECKS))),
                           user)
    except (ValueError, KeyError) as e:
        log_fn(f"WARN coverage audit unavailable ({e}); "
               "falling back to deterministic rules only")
        return []
    gaps = []
    for item in result.get("uncovered", []):
        claim = item.get("claim", "?")
        reason = item.get("reason", "")
        hint = item.get("suggested_check", "")
        gaps.append(f"Uncovered claim '{claim}': {reason}"
                    + (f" (consider check: {hint})" if hint else ""))
    return gaps


def enforce_coverage(client, story, doc, claims, decisions_text="",
                     log_fn=print):
    """Coverage guard (R6): criteria must express the story's claims.

    Deterministic rules first (always authoritative); then one strict LLM
    audit. Any gap triggers ONE corrective criteria re-draft; persistent
    gaps return status 'uncovered' for the pipeline to escalate instead of
    burning a convergence loop on criteria that prove nothing.
    Returns (doc, status) with status in {"clean", "redrafted", "uncovered"}.
    """
    computable = [c["claim"] for c in claims.get("claims", [])
                  if c.get("classification") == "COMPUTABLE"]
    redrafted = False
    for attempt in range(MAX_COVERAGE_REDRAFTS + 1):
        gaps = deterministic_gaps(doc, computable)
        if not gaps:
            gaps = audit_coverage(client, story, doc, computable, log_fn)
        if not gaps:
            return doc, ("redrafted" if redrafted else "clean")
        if attempt < MAX_COVERAGE_REDRAFTS:
            log_fn(f"Coverage guard: {len(gaps)} gap(s); corrective re-draft...")
            for g in gaps:
                log_fn(f"  - {g}")
            notes = (decisions_text or ""
                     + "\n\nCOVERAGE GAPS - the criteria above were rejected "
                     "because they do not express these claims. Add criteria "
                     "(with proper checks and parameters) that would FAIL if "
                     "each claim below were false:\n- "
                     + "\n- ".join(gaps))
            doc = draft_criteria(client, story, notes, log_fn=log_fn)
            redrafted = True
    log_fn("Coverage guard: gaps persist after corrective re-draft.")
    return doc, "uncovered"


def draft_criteria(client, story, decisions_text="", criteria_path=None, log_fn=print):
    """LLM drafts criteria JSON; contract validation rejects malformed output."""
    system = load_prompt("decompose", user_decisions=decisions_text or "none", story=story)
    doc = chat_json(client, "decompose", system, "Produce the criteria JSON now.")

    if criteria_path:
        Path(criteria_path).write_text(json.dumps(doc, indent=2), encoding="utf-8")

    validated = validate_criteria_doc(_as_criteria_doc(doc))
    log_fn(f"Drafted {len(validated['criteria'])} criteria: "
           + ", ".join(c["id"] for c in validated["criteria"]))
    return validated


def _as_criteria_doc(doc):
    """Accept both full-document and nested {'criteria': [...]} LLM shapes."""
    if "criteria" in doc and isinstance(doc["criteria"], list):
        return {
            "definitions": doc.get("definitions", {}),
            "criteria": doc["criteria"],
        }
    raise ValueError("LLM output missing 'criteria' list")
