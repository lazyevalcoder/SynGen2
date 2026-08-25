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


def _normalize_audit_item(item, known_checks):
    """Normalize one auditor gap to the graduated classification.

    New contract: explicit PARAMETRIC / VOCAB_GAP / QUALIFIER with an
    existing_check for PARAMETRIC. Legacy shape (suggested_check only) is
    mapped: a valid check name implies PARAMETRIC; anything else - including
    hallucinated names (benchmark F9.2) - degrades to VOCAB_GAP, which
    notes instead of blocking.
    """
    claim = item.get("claim", "?")
    reason = item.get("reason", "")
    classification = item.get("classification")
    check = item.get("existing_check") or item.get("suggested_check") or None
    if classification not in ("PARAMETRIC", "VOCAB_GAP", "QUALIFIER"):
        classification = ("PARAMETRIC" if check in known_checks
                          else "VOCAB_GAP")
    if classification == "PARAMETRIC" and check not in known_checks:
        # auditor violated the naming contract - degrade to note, log loudly
        classification = "VOCAB_GAP"
        reason += " [auditor named a non-existent check; treated as vocab gap]"
        check = None
    if classification != "PARAMETRIC":
        check = None
    return {"claim": claim, "reason": reason,
            "classification": classification, "check": check}


def audit_coverage_structured(client, story, doc, computable_claims,
                              log_fn=print):
    """LLM audit returning classified gaps.

    Returns (gaps, covered_claims) where gaps carry the normalized
    classification. Fails OPEN on transport/parse errors: returns
    (None, None) so the caller keeps deterministic rules authoritative
    without inventing coverage knowledge.
    """
    if not computable_claims:
        return [], []
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
        return None, None
    gaps = [_normalize_audit_item(item, set(CHECKS))
            for item in result.get("uncovered", [])]
    return gaps, list(result.get("covered", []))


def format_gap(gap):
    text = (f"Uncovered claim '{gap['claim']}' "
            f"[{gap['classification']}]: {gap['reason']}")
    if gap.get("check"):
        text += f" (consider check: {gap['check']})"
    return text


def audit_coverage(client, story, doc, computable_claims, log_fn=print):
    """Compat wrapper: string-formatted gaps from the structured audit."""
    gaps, _ = audit_coverage_structured(client, story, doc,
                                        computable_claims, log_fn)
    if gaps is None:
        return []
    return [format_gap(g) for g in gaps]


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
    """Graduated coverage guard (M6 P1, DOMAIN_PACKS.md): replaces the
    binary pass/escalate gate that killed 5 of 6 benchmark flights.

    Gap classes and their dispositions:
      - deterministic vacuous shapes (no criteria / generic-only):
        always blocking -> ESCALATE when they persist (near-zero coverage).
      - PARAMETRIC gaps (an existing check could prove the claim but the
        draft does not): trigger ONE bounded corrective re-draft with
        targeted feedback. Persistent parametric gaps with OTHER claims
        still covered = partial coverage -> PROCEED-WITH-NOTE.
      - VOCAB_GAP / QUALIFIER: never fatal; logged as coverage notes
        (roadmap signals), never block a flight.
      - coherence violations (mathematically impossible criteria):
        redraft-worthy; persistent ones ESCALATE - impossible math cannot
        ship honestly.
    Returns (doc, status), status in {"clean", "redrafted",
    "proceeded_with_notes", "uncovered"}.
    """
    computable = [c["claim"] for c in claims.get("claims", [])
                  if c.get("classification") == "COMPUTABLE"]
    redrafted = False
    for attempt in range(MAX_COVERAGE_REDRAFTS + 1):
        fatal = deterministic_gaps(doc, computable)
        audit_gaps, covered, coherence = [], None, []
        if not fatal:
            audit_gaps, covered = audit_coverage_structured(
                client, story, doc, computable, log_fn)
        if not fatal:
            coherence = coherence_gaps(doc)

        parametric = [g for g in (audit_gaps or [])
                      if g["classification"] == "PARAMETRIC"]
        notes = [g for g in (audit_gaps or [])
                 if g["classification"] in ("VOCAB_GAP", "QUALIFIER")]
        zero_coverage = (audit_gaps is not None and computable
                         and not covered)

        if not fatal and not parametric and not coherence and not zero_coverage:
            _log_notes(notes, log_fn)
            if redrafted:
                return doc, "redrafted"
            return doc, ("proceeded_with_notes" if notes else "clean")

        if attempt < MAX_COVERAGE_REDRAFTS:
            feedback = list(fatal) + list(coherence) + \
                [format_gap(g) for g in parametric]
            if zero_coverage:
                feedback.append(
                    "The criteria express NONE of the story's computable "
                    "claims. Add criteria (with proper checks and "
                    "parameters) that would FAIL if each claim were false.")
            if feedback:
                log_fn(f"Coverage guard: {len(feedback)} gap(s); "
                       "corrective re-draft...")
                for g in feedback:
                    log_fn(f"  - {g}")
                notes_text = (decisions_text or ""
                              + "\n\nCOVERAGE GAPS - the criteria above were "
                              "rejected because they do not express these "
                              "claims. Add criteria that would FAIL if each "
                              "claim below were false:\n- "
                              + "\n- ".join(feedback))
                doc = draft_criteria(client, story, notes_text,
                                     log_fn=log_fn)
                redrafted = True
                continue

        # redraft budget exhausted (or nothing actionable to redraft on)
        if fatal or zero_coverage or coherence:
            log_fn("Coverage guard: blocking gaps persist after "
                   "corrective re-draft.")
            return doc, "uncovered"
        _log_notes(notes + parametric, log_fn)
        return doc, "proceeded_with_notes"


def _log_notes(gaps, log_fn):
    """VOCAB_GAP/QUALIFIER items surface as notes, never as failures."""
    if not gaps:
        return
    log_fn(f"Coverage guard: {len(gaps)} note(s) - proceeding:")
    for g in gaps:
        log_fn(f"  [note] {format_gap(g)}")


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
