"""The M2 vertical slice + M3 sessions: story in -> landed dataset out.

Orchestrator is a deterministic state machine (AGENT_ROLES); judgment lives in
named phases. I/O is injected so tests can run the whole flow offline.
"""
import json
from pathlib import Path

from syngen.config import (ConfigError, load_criteria, load_json,
                           validate_simulator_doc)
from syngen.generator.engine import generate_to_workbook
from syngen.llm.client import BudgetExceeded
from syngen.linter import has_blocking, lint, structure_findings
from syngen.phases.amend import (
    apply_amendments,
    apply_criterion_overrides,
    apply_structured_amendments,
    consistency_report,
    dependency_closure,
)
from syngen.phases.converge import LoopEscalation, run_convergence
from syngen.phases.critic import (block_issues, critique_artifact,
                                  corrective_brief as critic_corrective_brief,
                                  render_issues)
from syngen.phases.defect_response import defect_response
from syngen.phases.criteria_lint import (corrective_brief, cross_lint,
                                         lint_criteria_internal,
                                         render_lint)
from syngen.phases.diff import RoutingError, classify_story_change, validate_route
from syngen.phases.intake import (
    draft_criteria,
    enforce_coverage,
    precheck_claims,
)
from syngen.phases.rework import (judge_revision, make_evidence,
                                  recover_criteria_consistency,
                                  redraft_criteria)
from syngen.phases.spec import draft_simulator, persona_critique
from syngen.session import Session
from syngen.utils import set_at_path
from syngen.validator.checks import CHECKS
from syngen.validator.report import render_table, run_validation, to_report_dict


class ConsoleIO:
    """Interactive terminal I/O."""

    @staticmethod
    def _safe_print(text):
        """LLM output can contain any unicode; Windows consoles are cp1252."""
        try:
            print(text)
        except UnicodeEncodeError:
            print(str(text).encode("ascii", errors="replace").decode("ascii"))

    def inform(self, text):
        self._safe_print(text)

    def confirm(self, prompt, default=True):
        suffix = " (Y/n)" if default else " (y/N)"
        answer = input(prompt + suffix + ": ").strip().lower()
        if not answer:
            return default
        return answer in ("y", "yes")

    def ask(self, prompt, default=""):
        answer = input(f"{prompt} [{default}]: ").strip()
        return answer or default

    def free_text(self, prompt):
        print(prompt)
        lines = []
        while True:
            line = input("> ")
            if not line.strip():
                break
            lines.append(line)
        return "\n".join(lines)


def criteria_summary(doc):
    return "\n".join(
        f"{c['id']} {c['name']} params={json.dumps(c['params'])}"
        for c in doc["criteria"]
    )


def simulator_summary(cfg):
    acc = cfg.get("accounts", {})
    opp = cfg.get("opportunities", {})
    return (f"accounts: count={acc.get('count')}, "
            f"regions={json.dumps(acc.get('regions', {}))}, "
            f"segments={json.dumps(acc.get('segments', {}))}, "
            f"industries={acc.get('industries', [])}; "
            f"opportunities: {opp.get('per_quarter')}/quarter over "
            f"{len(cfg.get('time_model', {}).get('quarter_labels', []))} quarters")


TAXONOMY_CONTAINERS = {
    "accounts.segments": "segments",
    "accounts.regions": "regions",
}


def apply_taxonomy_edits(cfg, edits):
    """Apply categorical container edits; renormalize probability dicts to 1.0.

    Container-level replacements must be dicts of weights - live run 1 caught
    the LLM proposing a bare list, which would silently destroy the weights.
    Returns (cfg, applied, warnings).
    """
    applied, warnings = [], []
    for ch in edits or []:
        path = ch.get("path", "")
        value = ch.get("value")
        try:
            if path in TAXONOMY_CONTAINERS:
                dim = TAXONOMY_CONTAINERS[path]
                if not isinstance(value, dict) or not value:
                    warnings.append(
                        f"rejected edit '{path}': replacing the whole "
                        f"{dim} container requires a dict of weights")
                    continue
                # Live-M3 lesson #2: the classifier replaced the container
                # and silently RENAMED values (Enterprise -> ENT). Existing
                # values must survive a replacement; only additions and
                # weight changes are legitimate taxonomy edits.
                dropped = set(cfg["accounts"][dim]) - {str(k) for k in value}
                if dropped:
                    warnings.append(
                        f"rejected edit '{path}': it removes/renames "
                        f"existing values {sorted(dropped)}; propose one "
                        f"leaf-path addition per new value instead")
                    continue
                node = cfg["accounts"][dim]
                node.clear()
                node.update({str(k): float(v) for k, v in value.items()})
                applied.append({"path": path,
                                "from": f"<{len(node)} entries>",
                                "to": dict(node)})
            else:
                old = set_at_path(cfg, path, value)
                applied.append({"path": path, "from": old, "to": value})
        except (KeyError, IndexError, TypeError, ValueError) as e:
            warnings.append(f"could not apply edit {path}: {e}")

    # containers whose values are mixture weights must keep summing to 1
    # (numpy rejects p-sums off by >1e-8, so no rounding here)
    for dim in ("regions", "segments"):
        spec = cfg["accounts"].get(dim)
        if isinstance(spec, dict) and spec:
            total = sum(float(v) for v in spec.values())
            if abs(total - 1.0) > 1e-9:
                keys = list(spec)
                running = 0.0
                for k in keys[:-1]:
                    spec[k] = float(spec[k]) / total
                    running += spec[k]
                spec[keys[-1]] = 1.0 - running
                warnings.append(
                    f"accounts.{dim} weights rescaled to sum to 1.0 "
                    f"(was {total:.4f})")
    return cfg, applied, warnings


def gate_lint(io, session, sim_cfg, log):
    """Schema linter at Gate 1 (FR4). Blocking findings prevent generation.

    Clean draft  -> confirm to proceed; decline exits to manual editing.
    Blocked draft -> user may fix simulator.json on disk and reload.
    Returns sim_cfg to proceed with, or None for the manual-edit exit.
    """
    while True:
        findings = lint(sim_cfg)
        for rule, sev, msg in findings:
            marker = "BLOCK" if sev != "ADVISE" else "ADVISE"
            log(f"  LINT [{rule}/{sev}] {msg}")
        blocked = has_blocking(findings)
        session.write_artifact("simulator.json", json.dumps(sim_cfg, indent=2))
        if not blocked:
            if io.confirm("Accept simulator.json knobs and start generating?"):
                log("Lint gate passed.")
                return sim_cfg
            log("Edit session simulator.json manually, then re-run convergence.")
            return None
        if io.confirm("Draft is BLOCKED by lint rules. Edit simulator.json on "
                      "disk now and continue when done?", default=False):
            sim_cfg = validate_simulator_doc(load_json(
                session.root / "simulator.json"))
            continue
        log("Edit session simulator.json manually, then re-run convergence.")
        return None


def calibrate_gate(client, io, story, crit_summary, spec_notes, doc,
                   sim_cfg, session, log, checks=None, split=False):
    """Pre-flight calibration (F17): deterministic config-vs-criteria
    cross-check before any iteration burns. HARD findings trigger one
    corrective re-draft; persistent HARD findings abort the session
    early with a precise reason instead of a doomed convergence loop.
    Returns (sim_cfg, status); sim_cfg None means abort."""
    from syngen.phases.preflight import (autocalibrate, calibrate,
                                         hard_findings, render_findings,
                                         repair_criteria)

    repairs = repair_criteria(sim_cfg, doc)
    if repairs:
        log("Repaired criteria deterministically:\n"
            + "\n".join(f"  - {x}" for x in repairs))
        session.log("## Criteria repair\n" + "\n".join(f"- {x}" for x in repairs))
        session.write_artifact("criteria.json", json.dumps(doc, indent=2))

    def run_pass(cfg):
        return calibrate(cfg, doc)

    def evaluate(cfg):
        """Calibrate + deterministically auto-fix (ALWAYS - even a
        findings-free draft may be missing planning synthesis like
        attainment ratios or a required quota block)."""
        f = run_pass(cfg)
        try:
            fx = autocalibrate(cfg, doc)
        except ConfigError as e:
            # P5 WP4: solver precondition violations (e.g. effective_capacity
            # naming an absent capacity unit) become corrective findings,
            # never crashes.
            return [{"rule": "PF0", "severity": "HARD", "criterion": "*",
                     "msg": str(e)}], []
        if fx:
            log("Auto-calibrated " + f"{len(fx)} item(s) deterministically:"
                + "\n" + "\n".join(f"  - {x}" for x in fx))
            session.log("## Auto-calibration\n" +
                        "\n".join(f"- {x}" for x in fx))
            (session.root / "simulator.json").write_text(
                json.dumps(cfg, indent=2), encoding="utf-8")
            f = run_pass(cfg)
        return f, fx

    findings, fixes = evaluate(sim_cfg)
    if not findings:
        return sim_cfg, ("autocalibrated" if fixes else "clean"), []
    log("Pre-flight calibration findings:\n" + render_findings(findings))
    session.log("## Pre-flight calibration\n```\n"
                + render_findings(findings) + "\n```")

    # Bounded corrective re-drafts (F17): the drafter converges on the
    # share/margin calculus across attempts (live s8c: 14pp -> 8pp miss
    # after one redraft). Keep drafting while HARD findings strictly
    # shrink; escalate the moment a draft fails to improve or the
    # budget is spent.
    max_redrafts = 3
    drafts_done = 0
    prev_hard_count = None
    while True:
        hard = hard_findings(findings)
        if not hard:
            if findings:
                log("Residual soft warnings:\n" + render_findings(findings))
            log("Pre-flight calibration passed.")
            session.log("PREFLIGHT passed "
                        f"({drafts_done} corrective re-drafts).")
            return sim_cfg, ("redrafted" if drafts_done else "soft_warnings"), []
        if prev_hard_count is not None and len(hard) >= prev_hard_count:
            log(f"HARD findings did not shrink ({len(hard)} >= "
                f"{prev_hard_count}) - escalating early.")
            session.log("PREFLIGHT FAILED: no improvement across "
                        "corrective drafts: " + json.dumps(hard))
            return None, "hard_findings_persist", hard
        if drafts_done >= max_redrafts:
            log("Corrective re-draft budget exhausted.")
            session.log("PREFLIGHT FAILED after re-draft budget: "
                        + json.dumps(hard))
            return None, "hard_findings_persist", hard
        log(f"{len(hard)} HARD finding(s) - corrective re-draft...")
        fix_notes = (spec_notes + "\n\nCORRECTIVE FINDINGS from pre-flight "
                     "calibration - fix ALL of these in the new draft:\n"
                     + render_findings(hard))
        try:
            sim_cfg = draft_simulator(client, story, crit_summary, fix_notes,
                                      checks=checks, split=split)
        except ConfigError as e:
            # P15: a corrective re-draft that cannot produce a valid config
            # must escalate, not crash the CLI (scenario 14 with DeepSeek).
            log(f"Corrective config re-draft failed ({e}) - escalating.")
            session.log("PREFLIGHT FAILED: corrective re-draft raised: "
                        + str(e))
            return None, "hard_findings_persist", hard
        doc.setdefault("definitions", {})["quarter_end_dates"] = dict(
            zip(sim_cfg["time_model"]["quarter_labels"],
                sim_cfg["time_model"]["quarter_end_dates"]))
        session.write_artifact("criteria.json", json.dumps(doc, indent=2))
        sim_cfg = gate_lint(io, session, sim_cfg, log)
        if sim_cfg is None:
            return None, "manual_edit", hard
        prev_hard_count = len(hard)
        drafts_done += 1
        findings, _ = evaluate(sim_cfg)
        log("Re-drafted calibration:\n" + render_findings(findings))


def post_generate_structure_gate(workbook_path, log, cfg=None):
    """Post-generation structural check (FR4): workbook must match the
    engine contract exactly (columns depend on optional config blocks).
    Returns (ok, findings) so callers can carry the mismatch into evidence."""
    findings = structure_findings(workbook_path, cfg=cfg)
    for rule, sev, msg in findings:
        log(f"  STRUCTURE [{rule}/{sev}] {msg}")
    return not has_blocking(findings), findings


def run_new_story(client, story, io, sessions_dir="sessions", slug=None,
                  max_iterations=10, max_llm_proposals=8, use_personas=False,
                  use_critic=True, max_rework_rounds=0,
                  rework_strategy="classic", use_capability=False,
                  stage23="classic"):
    """use_personas defaults OFF: the M4 A/B (experiments/M4_persona_ab)
    found no measurable quality benefit and a consistent ~35s latency cost.
    The P5 critic (use_critic) defaults ON: two bounded verification calls
    that catch intent errors (dropped claims, direction inversions) the
    deterministic gates cannot see.

    max_rework_rounds: the flexible stage-rework budget (P7). 0 = rigid
    one-way pipeline (legacy behavior, tests depend on exact call counts);
    >0 lets an LLM judge route escalation evidence back to criteria or
    config drafting before the flight ends. run_fly enables 2.

    rework_strategy: "classic" (full re-draft with the whole prompt) or
    "defect_response" (work order -> runbook/fixer -> verify). The latter is
    the experimental path; default stays classic.

    stage23: "classic" (one big prompt per stage) or "split" (P11: stage 2
    claim-form -> params; stage 3 core -> per-block, assembled in code)."""
    session = Session.create(sessions_dir, slug=slug or story[:40])
    log = io.inform
    session.save_story(story)
    log(f"Session: {session.root}")
    try:
        result = _run_pipeline(session, client, io, story, log,
                               fresh_criteria=True,
                               max_iterations=max_iterations,
                               max_llm_proposals=max_llm_proposals,
                               use_personas=use_personas,
                               use_critic=use_critic,
                               max_rework_rounds=max_rework_rounds,
                               rework_strategy=rework_strategy,
                               use_capability=use_capability,
                               stage23=stage23)
    except BudgetExceeded as e:
        # P18: a budget stop is an honest escalation, not a crash.
        log(f"BUDGET EXCEEDED: {e}")
        session.log(f"ESCALATED: budget_exceeded - {e}")
        result = {"status": "escalated", "reason": "budget_exceeded",
                  "session": str(session.root)}
    from syngen.usage import render_usage, write_usage
    result["llm_usage"] = write_usage(session, client)
    log(render_usage(result["llm_usage"]))
    return result


def run_resume(session_root, client, io, new_story=None,
               max_iterations=10, max_llm_proposals=8):
    """Return to an existing session: regenerate as-is, or classify a tweak."""
    session = Session.open(session_root)
    log = io.inform
    log(f"Resumed session: {session.root}")

    root = session.root
    criteria_path = root / "criteria.json"
    sim_path = root / "simulator.json"
    missing = [p.name for p in (criteria_path, sim_path) if not p.exists()]
    if missing:
        log(f"Session is incomplete; missing {missing}. Cannot resume - "
            "start a new session instead.")
        return {"status": "invalid_session"}

    if new_story is None:
        log("No new story given: regenerating from the existing config.")
        doc = load_criteria(criteria_path)
        return _converge_and_deliver(session, client, io, doc, sim_path, log,
                                     max_iterations, max_llm_proposals)

    # --- classify the tweak ---
    old_story = session.latest_story()
    if new_story.strip() == old_story.strip():
        # Live-M3 lesson: resubmitting identical text burned an LLM call and
        # created a redundant version just to hear "no diff".
        log("New story is identical to the latest version - "
            "treating as regenerate-as-is.")
        return _converge_and_deliver(session, client, io,
                                     load_criteria(criteria_path), sim_path,
                                     log, max_iterations, max_llm_proposals)
    n = session.save_story(new_story)
    log(f"Story saved as story.v{n}.md")
    doc = load_criteria(criteria_path)
    cfg = json.loads(sim_path.read_text(encoding="utf-8"))

    try:
        routed = classify_story_change(
            client, old_story, new_story,
            criteria_summary(doc), simulator_summary(cfg), log_fn=log)
    except (RoutingError, ValueError) as e:
        log(f"Classifier failed ({e}); escalating to structural.")
        routed = {"route": "structural", "notes": str(e)}
    try:
        routed = validate_route(routed, {c["id"] for c in doc["criteria"]})
    except RoutingError as e:
        log(f"Routing guardrails rejected the proposal ({e}); "
            "treating as structural.")
        routed = {"route": "structural", "notes": str(e)}

    route = routed["route"]
    session.write_artifact("story_diff.json", json.dumps(routed, indent=2))
    session.log(f"## Story diff v{n}: route={route}\n"
                f"```json\n{json.dumps(routed, indent=2)}\n```")

    if route == "structural":
        reason = routed.get("notes") or "new entities/behaviors required"
        session.log(f"RESUME escalated: structural ({reason})")
        log("\nSTRUCTURAL CHANGE: the current data model cannot express this. "
            "Start a fresh session ('syngen new'); carry over what you need.")
        return {"status": "escalated", "reason": "structural",
                "detail": reason, "session": str(root)}

    if route == "taxonomy":
        cfg, applied, warns = apply_taxonomy_edits(
            cfg, routed.get("proposed_config_edits", []))
        for w in warns:
            log(f"  NOTE {w}")
        change_str = "\n".join(
            f"  {a['path']}: {a['from']} -> {a['to']}" for a in applied)
        log(f"Taxonomy edits:\n{change_str}")
        if not applied or not io.confirm("Apply these taxonomy edits?"):
            log("Aborted at taxonomy review.")
            return {"status": "aborted", "where": "taxonomy_review"}
        sim_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    else:  # parametric
        amendments = routed.get("proposed_criteria_amendments", []) or []
        doc, applied, errors = apply_structured_amendments(doc, amendments)
        for e in errors:
            log(f"WARN unusable amendment skipped: {json.dumps(e)}")
        changed_ids = sorted({a["id"] for a in applied})
        affected = dependency_closure(doc["criteria"], changed_ids) \
            if changed_ids else []
        _print_criteria(io, doc)
        if applied:
            log("Amended: " + ", ".join(changed_ids))
            if affected:
                log(f"Dependency propagation: {', '.join(affected)} also "
                    "affected - re-review above before signing off.")
            log("Dependency edges:\n" + consistency_report(doc))
        if not io.confirm("Sign off amended criteria?", default=True):
            log("Aborted at Gate 1 re-approval.")
            return {"status": "aborted", "where": "gate1_reapproval"}
        session.log("GATE 1 re-approval passed after amendment.")
        criteria_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    return _converge_and_deliver(session, client, io, doc, sim_path, log,
                                 max_iterations, max_llm_proposals)


def _converge_and_deliver(session, client, io, doc, sim_path, log,
                          max_iterations, max_llm_proposals):
    """Shared tail of both flows: converge, structure-gate, deliver.
    Escalations return with an `evidence` packet (P7) so the rework judge
    can route the next attempt."""
    criteria_path = session.root / "criteria.json"
    try:
        summary = run_convergence(session, client, sim_path, criteria_path,
                                  max_iterations=max_iterations,
                                  max_llm_proposals=max_llm_proposals,
                                  log_fn=log)
    except LoopEscalation as esc:
        session.log(f"ESCALATED: {esc.reason}")
        log(f"\nNEEDS YOUR ATTENTION: {esc.reason}")
        margins = {}
        for r in esc.results or []:
            if r.get("verdict") != "PASS" and r.get("margin") is not None:
                margins[r.get("id")] = round(float(r["margin"]), 2)
        evidence = make_evidence("convergence", esc.reason, doc,
                                 margins=margins,
                                 detail="tuning loop could not satisfy all criteria")
        return {"status": "escalated", "reason": esc.reason,
                "session": str(session.root), "evidence": evidence}

    sim_cfg = load_json(sim_path) if not isinstance(sim_path, dict) else sim_path
    ok, sfindings = post_generate_structure_gate(summary["workbook"], log,
                                                 cfg=sim_cfg)
    if not ok:
        session.log("STRUCTURE GATE FAILED")
        detail = "; ".join(msg for _, _, msg in sfindings)
        evidence = make_evidence("structure", "workbook schema mismatch",
                                 doc, detail=detail)
        return {"status": "structure_check_failed",
                "workbook": summary["workbook"], "evidence": evidence}

    results, all_pass = run_validation_final(summary, criteria_path)
    report_md = render_table(results, all_pass) if all_pass else "(see log)"
    session.write_artifact("validation_report.md", f"```\n{report_md}\n```\n")
    session.log("GATE 2 passed: delivered.")
    log(f"\nDeliverables in {session.root}")
    log(f"  dataset:   {summary['workbook']}")
    log(f"  proof:     validation_report.md")
    log(f"  config:    simulator.json (tweak knobs anytime, regenerate)")
    if summary.get("thin_margins"):
        log(f"  note: thin margins on {', '.join(summary['thin_margins'])}")
    loose_margins = [r["id"] for r in results if r.get("loose")]
    if loose_margins:
        log(f"  note: LOOSE margins on {', '.join(loose_margins)} - landed "
            "but the data may overshoot the story (see validation_report.md)")
    if not io.confirm("Inspect and accept delivery?", default=True):
        return {"status": "delivered_unaccepted", "session": str(session.root)}
    return {"status": "converged", "session": str(session.root),
            "iterations": summary["iterations"],
            "llm_proposals": summary["llm_proposals"],
            "thin_margins": summary["thin_margins"],
            "loose_margins": loose_margins}


def _capability_workbench(session, client, story, doc, claims, decisions_text,
                          sim_cfg, log, max_rounds=3):
    """Give the drafter the engine's numbers, then clamp what it still misses.

    Bounded by construction: at most `max_rounds` LLM re-drafts (claim-
    preserving), then a single deterministic snap pass - it can never loop.
    Returns (doc, adjustments)."""
    from syngen.capability import assess_config, snap_criteria
    adjustments = []
    for rnd in range(max(0, max_rounds)):
        findings = assess_config(sim_cfg, doc)
        bad = [f for f in findings if f.get("reachable") is False]
        if not bad:
            return doc, adjustments
        lines = []
        for f in bad:
            if f.get("param") and f.get("nearest") is not None:
                lines.append(
                    f"- {f['id']} ({f['check']}): target {f['target']} is out "
                    f"of range - {f['note']}. Use {f['nearest']} instead.")
            else:
                lines.append(
                    f"- {f['id']} ({f['check']}): not buildable - {f['note']}. "
                    "Re-express the SAME claim with a reachable check.")
        log(f"Capability workbench round {rnd + 1}/{max_rounds}: "
            f"{len(bad)} unbuildable criterion(s) - re-drafting with numbers.")
        session.log("## Capability workbench\n" + "\n".join(lines))
        new_doc, ok = redraft_criteria(
            client, story, doc, claims, decisions_text,
            "CAPABILITY CORRECTIONS (the engine cannot build these as "
            "drafted - fix them using the numbers):\n" + "\n".join(lines),
            log_fn=log)
        if not ok:
            log("Capability workbench re-draft lost coverage - stopping the "
                "loop and clamping instead.")
            break
        doc = new_doc
    # Deterministic clamp for whatever is still unreachable (one pass).
    doc, adjustments = snap_criteria(doc, sim_cfg)
    if adjustments:
        log(f"Capability snap: {len(adjustments)} target(s) clamped to the "
            "nearest buildable value (recorded for Gate-1 review).")
        session.log("## Capability snap (buildable by construction)\n"
                    + "\n".join(f"- {a['id']}.{a['param']}: {a['from']} -> "
                                f"{a['to']} ({a['reason']})"
                                for a in adjustments))
        session.write_artifact("criteria.json", json.dumps(doc, indent=2))
    return doc, adjustments


def _geometry_corrective(session, client, story, doc, claims, decisions_text,
                         sim_cfg, log, feasibility=True):
    """P5 WP3 / P6 P1.3 / P8: one bounded corrective criteria re-draft for
    coordinate-geometry findings. Returns (doc, escalated_result_or_None)."""
    geo_findings = cross_lint(sim_cfg, doc, feasibility=feasibility)
    if not geo_findings:
        return doc, None
    session.log("CRITERIA GEOMETRY LINT:\n" + render_lint(geo_findings))
    log("Criteria coordinates fall outside the drafted data model - "
        "one corrective re-draft.")
    geo_brief = ("CRITERIA GEOMETRY FINDINGS - fix ALL of these. "
                 "Reference only coordinates/units that exist in the "
                 "drafted data model, or re-express subset claims as a "
                 "spread/min-spread criterion or per-unit scoping "
                 "(a cohort pseudo-unit like 'top territories' cannot "
                 "be built):\n" + render_lint(geo_findings))
    doc = draft_criteria(client, story, decisions_text + "\n\n" + geo_brief)
    doc, cov_status2 = enforce_coverage(
        client, story, doc, claims, decisions_text=decisions_text, log_fn=log)
    lint_hard, _ = lint_criteria_internal(doc)
    geo_findings = cross_lint(sim_cfg, doc, feasibility=feasibility)
    if cov_status2 == "uncovered" or lint_hard or geo_findings:
        session.write_artifact("criteria.json", json.dumps(doc, indent=2))
        session.log("ESCALATED: criteria_geometry - criteria reference "
                    "coordinates outside the data model even after a "
                    "corrective re-draft.")
        log("\nNEEDS YOUR ATTENTION: criteria reference coordinates "
            "that do not exist in the drafted config, even after a "
            "corrective re-draft (see session log). criteria.json "
            "persisted for inspection.")
        evidence = make_evidence("geometry_persist", "criteria_geometry",
                                 doc, detail="; ".join(geo_findings)[:500])
        return doc, {"status": "escalated", "reason": "criteria_geometry",
                     "session": str(session.root), "evidence": evidence}
    session.log("CRITERIA GEOMETRY: corrective re-draft accepted.")
    session.write_artifact("criteria.json", json.dumps(doc, indent=2))
    return doc, None


def _is_structural_preflight(hard):
    """S10.2: a STRUCTURAL preflight failure is one where EVERY hard finding
    is a schema-invalid config (PF0 whose msg is 'config invalid: ...').

    Referential PF0s (e.g. a criterion naming a unit absent from the capacity
    block) are criteria/config mismatches the rework judge can route, so they
    are deliberately NOT structural."""
    return bool(hard) and all(
        f.get("rule") == "PF0"
        and str(f.get("msg", "")).startswith("config invalid")
        for f in hard)


def _delivery_attempt(session, client, io, story, doc, claims,
                      decisions_text, spec_notes, log, max_iterations,
                      max_llm_proposals, use_critic, guidance="",
                      use_capability=False, stage23="classic"):
    """One full post-criteria delivery attempt (P7): simulator draft ->
    critic B -> schema lint -> pre-flight calibration -> geometry lint ->
    converge -> structure gate -> deliver.

    Returns (result, doc, evidence). `doc` may be mutated (calendar sync,
    criteria repair, a geometry corrective re-draft). On escalation the
    result carries an `evidence` packet for the rework judge.
    """
    crit_summary = criteria_summary(doc)
    checks = [c["check"] for c in doc.get("criteria", [])]
    split = (stage23 == "split")
    sim_notes = ((spec_notes + "\n\n" + guidance).strip()
                 if guidance else spec_notes)

    def _draft_failed(e):
        # S22: draft_simulator is bounded now - a spent budget is a normal
        # escalation, not a crash/hang.
        evidence = make_evidence("draft_invalid",
                                 "simulator draft invalid after re-drafts",
                                 doc, detail=str(e))
        return ({"status": "escalated", "reason": "draft_invalid",
                 "session": str(session.root), "evidence": evidence},
                doc, evidence)

    try:
        sim_cfg = draft_simulator(client, story, crit_summary, sim_notes,
                                  checks=checks, split=split)
    except ConfigError as e:
        return _draft_failed(e)

    # --- Critic pass B (P5 WP9): config vs criteria semantics. Block
    # findings trigger exactly one corrective simulator re-draft.
    if use_critic:
        verdict = critique_artifact(client, story,
                                    "simulator.json (data generator config)",
                                    {"criteria": doc.get("criteria"),
                                     "simulator": sim_cfg})
        issues = block_issues(verdict)
        if issues:
            session.log("CRITIC (config) block findings:\n"
                        + render_issues(issues))
            log(f"Critic flagged {len(issues)} block issue(s) in the "
                "drafted config - one corrective re-draft.")
            try:
                sim_cfg = draft_simulator(
                    client, story, crit_summary,
                    (sim_notes or "") + "\n\n"
                    + critic_corrective_brief(issues),
                    corrective_findings=critic_corrective_brief(issues),
                    checks=checks, split=split)
            except ConfigError as e:
                return _draft_failed(e)

    # Calendar flows from the generator's config into criteria so validation
    # stays consistent with what the engine actually generated (live-smoke bug).
    doc.setdefault("definitions", {})["quarter_end_dates"] = dict(
        zip(sim_cfg["time_model"]["quarter_labels"],
            sim_cfg["time_model"]["quarter_end_dates"])
    )
    session.write_artifact("criteria.json", json.dumps(doc, indent=2))

    # --- Schema lint gate (FR4) ---
    sim_cfg = gate_lint(io, session, sim_cfg, log)
    if sim_cfg is None:
        return {"status": "manual_edit", "session": str(session.root)}, doc, None

    # --- Capability workbench (stage 2/3): give the drafter the engine's
    # numbers, then clamp what it still misses (bounded; can never loop).
    if use_capability:
        doc, cap_adjust = _capability_workbench(
            session, client, story, doc, claims, decisions_text, sim_cfg, log,
            max_rounds=3)
        crit_summary = criteria_summary(doc)

    # --- Criteria x config COORDINATE geometry (P8): run BEFORE calibration
    # so a criterion referencing a non-existent unit (e.g. a pseudo-cohort
    # like `segment: core_ex_whales`) is re-drafted as CRITERIA instead of
    # dead-looping preflight's referential gate on config re-drafts.
    doc, esc = _geometry_corrective(
        session, client, story, doc, claims, decisions_text, sim_cfg, log,
        feasibility=False)
    if esc is not None:
        return esc, doc, esc.get("evidence")

    # --- Pre-flight calibration gate (F17) ---
    sim_cfg, status, hard = calibrate_gate(client, io, story, crit_summary,
                                           sim_notes, doc, sim_cfg, session, log,
                                           checks=checks, split=split)
    if sim_cfg is None:
        # S10.2: a STRUCTURAL failure (rule PF0 = the config itself is invalid)
        # is not a criteria problem. Deterministic repair already ran inside
        # the gate; if the config is still invalid, route it honestly instead
        # of letting the LLM judge misattribute it to a criteria ceiling.
        # Carry the REAL findings so the report names the cause.
        from syngen.phases.preflight import render_findings
        structural = _is_structural_preflight(hard)
        detail = (render_findings(hard) if hard else
                  "deterministic calibration could not make the config "
                  "satisfy the criteria")
        kind = "preflight_structural" if structural else "preflight_persist"
        reason = ("preflight_structural" if structural
                  else "preflight_calibration")
        evidence = make_evidence(kind, f"preflight calibration: {status}", doc,
                                 detail=detail)
        return {"status": "escalated", "reason": reason,
                "session": str(session.root), "evidence": evidence}, doc, evidence

    # --- Criteria x config geometry + feasibility (P5 WP3): coordinates must
    # land inside the drafted/synthesized data model before the loop starts.
    doc, esc = _geometry_corrective(
        session, client, story, doc, claims, decisions_text, sim_cfg, log,
        feasibility=True)
    if esc is not None:
        return esc, doc, esc.get("evidence")

    result = _converge_and_deliver(session, client, io, doc,
                                   session.root / "simulator.json", log,
                                   max_iterations, max_llm_proposals)
    return result, doc, result.get("evidence")


def _delivery_rework(session, client, io, story, doc, claims, decisions_text,
                     spec_notes, log, max_iterations, max_llm_proposals,
                     use_critic, max_rework_rounds, rework_strategy="classic",
                     use_capability=False, stage23="classic"):
    """Bounded rework coordinator (P7): run the delivery attempt; when it
    escalates with evidence, ask the LLM judge to route the next attempt
    back to criteria or config drafting. Deterministic guards (coverage vs
    the original claims, consistency lint) keep every rework claim-preserving,
    so a revision can never erode the story to force a landing."""
    directives = []
    cur_doc = doc
    guidance = ""
    for rnd in range(max_rework_rounds + 1):
        result, cur_doc, evidence = _delivery_attempt(
            session, client, io, story, cur_doc, claims, decisions_text,
            spec_notes, log, max_iterations, max_llm_proposals, use_critic,
            guidance=guidance, use_capability=use_capability, stage23=stage23)
        guidance = ""
        if result.get("status") in ("converged", "delivered_unaccepted",
                                    "manual_edit"):
            result["rework"] = {"rounds": rnd, "directives": directives}
            return result
        if rnd >= max_rework_rounds:
            session.log("REWORK budget exhausted "
                        f"({max_rework_rounds}); final escalation: "
                        f"{result.get('reason')}")
            result["rework"] = {"rounds": rnd, "directives": directives}
            return result
        if evidence is not None and \
                evidence.get("kind") == "preflight_structural":
            # S10.2: the config itself is invalid and deterministic repair
            # could not fix it. The LLM judge has no engine knowledge and
            # would misattribute this to a criteria ceiling - skip it and
            # escalate with the real (structural) cause.
            log("Structural preflight failure (config invalid) - criteria "
                "rework cannot fix it; escalating without a judge round.")
            session.log("REWORK skipped: structural preflight failure "
                        "(config invalid), not a criteria problem.")
            result["rework"] = {"rounds": rnd, "directives": directives}
            return result
        if evidence is None:
            evidence = make_evidence(
                "unknown", result.get("reason") or result.get("status")
                or "escalated", cur_doc)
        log(f"\nREWORK round {rnd + 1}/{max_rework_rounds}: escalation "
            f"({evidence.get('kind')}) - judging the revision...")
        verdict = judge_revision(client, story, evidence, cur_doc, rnd + 1,
                                 log_fn=log)
        directive = {"round": rnd + 1, "kind": evidence.get("kind"),
                     "escalation": result.get("reason"),
                     "action": verdict["action"], "scope": verdict["scope"],
                     "reason": verdict["reason"],
                     "guidance": verdict["guidance"]}
        directives.append(directive)
        session.log("REWORK verdict: " + json.dumps(directive, indent=1))
        if verdict["action"] == "escalate":
            log(f"Rework judge escalated: {verdict['reason'] or 'no revision helps'}")
            result["reason"] = f"{result.get('reason')} [judge: {verdict['reason'] or 'no revision credibly helps'}]"
            result["rework"] = {"rounds": rnd + 1, "directives": directives}
            return result
        if verdict["action"] == "rework_criteria":
            if rework_strategy == "defect_response":
                new_doc, ok, dr = defect_response(client, verdict, evidence,
                                                  cur_doc, log_fn=log)
                for key in ("defect_class", "targets", "resolver"):
                    if key in dr:
                        directive[key] = dr[key]
                if not ok:
                    log("Defect-response patch rejected by the guards "
                        f"({dr.get('resolver')}: {dr.get('reason')}) - final "
                        "escalation.")
                    result["rework"] = {"rounds": rnd + 1,
                                        "directives": directives}
                    return result
                cur_doc = new_doc
                session.write_artifact("criteria.json",
                                       json.dumps(cur_doc, indent=2))
                log(f"Defect-response {dr.get('resolver')} patch applied "
                    f"(round {rnd + 1}) - retrying delivery.")
                continue
            new_doc, ok = redraft_criteria(client, story, cur_doc, claims,
                                           decisions_text,
                                           verdict["guidance"], log_fn=log)
            if not ok:
                log("Criteria rework rejected by the claim-preservation "
                    "guards - final escalation.")
                result["rework"] = {"rounds": rnd + 1,
                                    "directives": directives}
                return result
            cur_doc = new_doc
            session.write_artifact("criteria.json",
                                   json.dumps(cur_doc, indent=2))
            log(f"Criteria re-drafted (round {rnd + 1}) - retrying delivery.")
            continue
        # rework_config: steer the next attempt's simulator draft.
        guidance = ("PREVIOUS ATTEMPT's config could not satisfy the "
                    "criteria. Fix these in the simulator draft:\n"
                    + (verdict["guidance"] or verdict["reason"]))
        log(f"Config rework ordered (round {rnd + 1}) - retrying delivery.")

    return {"status": "escalated", "reason": "rework exhausted",
            "session": str(session.root),
            "rework": {"rounds": max_rework_rounds, "directives": directives}}


def _run_pipeline(session, client, io, story, log, fresh_criteria=True,
                  max_iterations=10, max_llm_proposals=8, use_personas=True,
                  use_critic=True, max_rework_rounds=0,
                  rework_strategy="classic", use_capability=False,
                  stage23="classic"):
    """Fresh-story flow: pre-check, Gate 1, personas+draft, then the
    delivery tail wrapped in the bounded rework coordinator (P7)."""
    # --- Pre-check ---
    claims = precheck_claims(client, story, log_fn=log)
    # P7: the original claims are the anti-goalpost floor for any later
    # criteria rework - persist them now so rework can re-verify coverage.
    session.write_artifact("computable_claims.json",
                           json.dumps(claims, indent=2))
    for c in claims.get("claims", []):
        marker = "+" if c.get("classification") == "COMPUTABLE" else "-"
        log(f"  [{marker}] {c.get('claim')} - {c.get('note', '')[:90]}")
    for q in claims.get("questions_for_user", []):
        log(f"  ? {q}")
    if not io.confirm("Proceed with the computable claims above?"):
        log("Aborted at pre-check.")
        return {"status": "aborted", "where": "precheck"}

    # --- Gate 1: decompose + negotiate ---
    decisions_text = io.free_text(
        "Answer any pre-check questions now (blank line to finish), "
        "or leave empty:"
    )
    doc = draft_criteria(client, story, decisions_text, claims=claims,
                         split=(stage23 == "split"))

    # --- Coverage guard (M5 iter 5, R6): vacuous criteria never converge ---
    doc, cov_status = enforce_coverage(client, story, doc, claims,
                                       decisions_text=decisions_text,
                                       log_fn=log)
    if cov_status == "uncovered":
        # F5.3 (M6 P3): persist the rejected draft so the escalation is
        # diagnosable - the session previously held no criteria at all.
        session.write_artifact("criteria.json", json.dumps(doc, indent=2))
        session.log("ESCALATED: criteria_coverage - drafted criteria do not "
                    "express the story's computable claims. Draft persisted "
                    "to criteria.json for inspection.")
        log("\nNEEDS YOUR ATTENTION: the drafted criteria express none of "
            "the story's computable claims (even after a corrective "
            "re-draft). Review/extend criteria.json manually or re-run.")
        return {"status": "escalated", "reason": "criteria_coverage",
                "session": str(session.root)}
    if cov_status == "redrafted":
        session.log("COVERAGE GUARD: criteria re-drafted to cover the "
                    "story's claims.")
    if cov_status == "proceeded_with_notes":
        session.log("COVERAGE GUARD: proceeding with noted vocabulary/"
                    "qualifier gaps (see session log).")

    # --- Critic pass A (P5 WP9): criteria vs story intent. Block-severity
    # findings trigger exactly one corrective re-draft through the guard.
    if use_critic:
        verdict = critique_artifact(client, story, "acceptance criteria", doc)
        issues = block_issues(verdict)
        if issues:
            session.log("CRITIC (criteria) block findings:\n"
                        + render_issues(issues))
            log(f"Critic flagged {len(issues)} block issue(s) in the "
                "drafted criteria - one corrective re-draft.")
            doc = draft_criteria(client, story,
                                 decisions_text + "\n\n"
                                 + critic_corrective_brief(issues))
            doc, cov_status = enforce_coverage(
                client, story, doc, claims, decisions_text=decisions_text,
                log_fn=log)
            if cov_status == "uncovered":
                session.write_artifact("criteria.json",
                                       json.dumps(doc, indent=2))
                session.log("ESCALATED: criteria_coverage after critic "
                            "re-draft.")
                return {"status": "escalated",
                        "reason": "criteria_coverage",
                        "session": str(session.root)}
            session.log("CRITIC: corrective criteria re-draft accepted.")

    # --- Criterion consistency lint (P5 WP2): provably unsatisfiable
    # criterion sets die here instead of after burning a flight ---
    lint_hard, lint_notes = lint_criteria_internal(doc)
    for note in lint_notes:
        log(f"  [lint] {note}")
    if lint_hard:
        session.log("CRITERION CONSISTENCY LINT:\n"
                    + render_lint(lint_hard))
        log("Criterion consistency violations (see session log) - "
            "one corrective re-draft.")
        doc = draft_criteria(client, story, decisions_text + "\n\n"
                             + corrective_brief(lint_hard))
        doc, cov_status2 = enforce_coverage(
            client, story, doc, claims, decisions_text=decisions_text,
            log_fn=log)
        lint_hard, _ = lint_criteria_internal(doc)
        if cov_status2 == "uncovered":
            session.write_artifact("criteria.json", json.dumps(doc, indent=2))
            session.log("ESCALATED: criteria_consistency - conflicting "
                        "criteria persisted past a corrective re-draft.")
            log("\nNEEDS YOUR ATTENTION: criteria are jointly "
                "unsatisfiable even after a corrective re-draft. See "
                "criteria.json.")
            return {"status": "escalated", "reason": "criteria_consistency",
                    "session": str(session.root)}
        # P8 S25.4: the lint used to be terminal after one re-draft, so a
        # conflicting set died at Gate 1 before the delivery-stage rework
        # loop could see it. Route it through the same bounded judge loop.
        if lint_hard and max_rework_rounds > 0:
            log("Criterion consistency still violated - routing through the "
                "bounded rework judge (P8).")
            doc, ok, g1_directives = recover_criteria_consistency(
                client, story, doc, claims, decisions_text, lint_hard,
                max_rework_rounds, log_fn=log)
            session.log("GATE-1 REWORK: " + json.dumps(g1_directives, indent=1))
            if ok:
                session.log("CRITERION CONSISTENCY: recovered by rework judge "
                            f"after {len(g1_directives)} round(s).")
                session.write_artifact("criteria.json",
                                       json.dumps(doc, indent=2))
                lint_hard = []
        if lint_hard:
            session.write_artifact("criteria.json", json.dumps(doc, indent=2))
            session.log("ESCALATED: criteria_consistency - conflicting "
                        "criteria persisted past a corrective re-draft.")
            log("\nNEEDS YOUR ATTENTION: criteria are jointly "
                "unsatisfiable even after a corrective re-draft. See "
                "criteria.json.")
            return {"status": "escalated", "reason": "criteria_consistency",
                    "session": str(session.root)}
        session.log("CRITERION CONSISTENCY: corrective re-draft accepted.")

    deps_note = consistency_report(doc).strip()
    if deps_note != "(no dependencies declared)":
        log("Declared dependencies:\n" + deps_note)
    _print_criteria(io, doc)

    overrides = ""
    while not io.confirm("Sign off these criteria?", default=True):
        overrides = io.ask("Overrides (e.g. AC3.target_pct=21, AC6.min_gap_pp=4)")
        try:
            doc, changed, affected = apply_amendments(doc, overrides)
            _print_criteria(io, doc)
            if affected:
                log(f"Dependency propagation: {', '.join(affected)} depend(s) "
                    f"on {', '.join(changed)} - re-review above before "
                    "signing off.")
        except ValueError as e:
            log(f"Could not apply override: {e}")

    criteria_path = session.write_artifact(
        "criteria.json", json.dumps(doc, indent=2))
    session.log("GATE 1 passed: criteria signed off.")
    log("Gate 1 passed.")

    # --- Phase 2: personas (lightweight) + simulator draft ---
    crit_summary = criteria_summary(doc)
    if use_personas:
        critique = persona_critique(client, story, crit_summary, log_fn=log)
        spec_lines = []
        for persona in ("domain_expert", "bi_engineer", "outsider"):
            for bullet in critique.get(persona, [])[:5]:
                spec_lines.append(f"- [{persona}] {bullet}")
    else:
        # A/B arm (G1): measure what the persona pass actually contributes
        log("Personas SKIPPED (A/B control arm)")
        spec_lines = []
    conflict_notes = io.free_text(
        "Resolve flagged conflicts (one per line, blank to finish):"
    )
    spec_notes = ("\n".join(spec_lines)
                  + f"\n\nUser resolutions:\n{conflict_notes}").strip()
    session.write_artifact("spec.md", f"# Data Spec\n\n{spec_notes or 'none'}\n")

    # --- Delivery tail, wrapped in the bounded rework coordinator (P7) ---
    return _delivery_rework(session, client, io, story, doc, claims,
                            decisions_text, spec_notes, log,
                            max_iterations, max_llm_proposals,
                            use_critic, max_rework_rounds, rework_strategy,
                            use_capability, stage23)


def run_validation_final(summary, criteria_path):
    wb = Path(summary["workbook"])
    return run_validation(wb, criteria_path)


def _print_criteria(io, doc):
    rows = []
    for c in doc["criteria"]:
        check_ok = c["check"] in CHECKS
        known = "" if check_ok else " [UNKNOWN CHECK]"
        depends = c.get("depends_on") or []
        dep_note = f" (depends_on: {', '.join(depends)})" if depends else ""
        rows.append(f"  {c['id']}  {c['name']}{known}{dep_note}\n"
                    f"       check={c['check']} params={json.dumps(c['params'])}")
    io.inform("\n".join(rows))
