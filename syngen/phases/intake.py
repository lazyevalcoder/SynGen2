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


def coherence_gaps(doc):
    """M5 iter 5 item 3 (R10): criteria sets that are mathematically
    impossible regardless of config knobs. Every rule here is
    config-independent and EXACT - raking makes attainment exact, so
    derived quantities must satisfy their algebraic constraints:

    - company-wide attainment is a PLAN-WEIGHTED MEAN of unit
      attainments, hence must lie within [min unit, max unit]
      (unlisted units count as 1.0);
    - ex-whale (core) attainment can never exceed headline attainment -
      whales only add revenue;
    - realized_vs_list is ~the complement of avg_discount_quarter for
      the same quarter: pinned values whose tolerance windows do not
      overlap cannot both hold.
    """
    criteria = doc.get("criteria", [])
    gaps = []
    by_check = {}
    for c in criteria:
        by_check.setdefault(c["check"], []).append(c)

    def att(c):
        return float(c.get("params", {}).get("target_pct", 100.0)) / 100.0

    rvp = by_check.get("revenue_vs_plan", [])
    units = {c["params"].get("segment"): att(c) for c in rvp
             if c["params"].get("segment") not in (None, "_all_")}
    all_crits = [c for c in rvp
                 if c["params"].get("segment") == "_all_"
                 and not c["params"].get("exclude_outlier_deals")]
    if units and all_crits:
        # unlisted plan units rake to the default 1.0, so they widen the
        # achievable range
        lo = min([*units.values(), 1.0])
        hi = max([*units.values(), 1.0])
        for c in all_crits:
            t = att(c)
            band = float(c["params"].get("band_pct", 2.0)) / 100.0
            if t > hi + band or t < lo - band:
                gaps.append(
                    f"{c['id']}: company-wide attainment {t:.2f} is "
                    f"outside the achievable range [{lo:.2f}, {hi:.2f}] "
                    "implied by the named-unit criteria (weighted means "
                    "cannot escape the unit range)")
    core_crits = [c for c in rvp
                  if c["params"].get("exclude_outlier_deals")]
    if core_crits and all_crits:
        head = min(att(c) for c in all_crits)
        for c in core_crits:
            if att(c) > head:
                gaps.append(
                    f"{c['id']}: ex-outlier (core) attainment "
                    f"{att(c):.2f} exceeds the headline attainment "
                    f"{head:.2f} - whales add revenue, so core can never "
                    "outgrow the total")
    disc = {}
    for c in by_check.get("avg_discount_quarter", []):
        q = c["params"].get("quarter")
        if q:
            disc[q] = (float(c["params"].get("target_pct", 0)),
                       float(c["params"].get("tolerance_pp", 4)), c["id"])
    for c in by_check.get("realized_vs_list", []):
        p = c["params"]
        tol = float(p.get("tolerance_pp", 3))
        for qkey, tkey in (("quarter_start", "target_start_pct"),
                           ("quarter_end", "target_end_pct")):
            q, want = p.get(qkey), p.get(tkey)
            if q not in disc or want is None:
                continue
            d_target, d_tol, did = disc[q]
            # realized ~= 100 - discount (+~2pp weighting bonus)
            implied_disc_hi = 100 - float(want) + tol + 2
            implied_disc_lo = 100 - float(want) - tol + 2
            if d_target > implied_disc_hi + d_tol or \
                    d_target < implied_disc_lo - d_tol:
                gaps.append(
                    f"{c['id']}/{did}: {q} pins realized/list ~{want:g}% "
                    f"(implied discount {implied_disc_lo:g}-{implied_disc_hi:g}%)"
                    f" but avg_discount targets {d_target:g}% +/-{d_tol:g}"
                    " - the two claims contradict")
    return gaps


def enforce_coverage(client, story, doc, claims, decisions_text="",
                     log_fn=print):
    """Coverage guard (R6) + coherence check (R10): criteria must express
    the story's claims AND be mutually satisfiable.

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
            gaps = coherence_gaps(doc)
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
