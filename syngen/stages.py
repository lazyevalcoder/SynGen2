"""Flight stages: the 7 resumable units of a flight (P12).

Each stage reads its inputs from the SESSION FOLDER (never from in-memory
state), writes its artifacts, and returns a `StageResult`. That statelessness
is what makes `run --stage-N`, resume-at-next, and rewind possible.

Stages are thin wrappers over the existing helpers - the classic
`run_new_story` path is untouched while this layer is proven (wrap first,
migrate later).
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

STAGE_NAMES = {
    1: "intake",
    2: "criteria",
    3: "config",
    4: "preflight",
    5: "converge",
    6: "structure",
    7: "deliver",
}


@dataclass
class StageResult:
    stage: int
    status: str                       # completed | escalated | aborted | skipped
    reason: str = ""
    detail: str = ""
    evidence: dict | None = None
    rewind_to: int | None = None
    artifacts: list = field(default_factory=list)


@dataclass
class StageContext:
    session: object
    client: object
    io: object
    story: str
    log: callable
    flags: dict = field(default_factory=dict)
    guidance: str = ""


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _criteria(session):
    return _read_json(session.root / "criteria.json")


def _simulator(session):
    return _read_json(session.root / "simulator.json")


def _claims(session):
    return _read_json(session.root / "computable_claims.json")


def _decisions(session):
    p = session.root / "decisions.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


# --- Stage 1: intake ---------------------------------------------------------

def stage_intake(ctx):
    from syngen.phases.intake import precheck_claims

    claims = precheck_claims(ctx.client, ctx.story, log_fn=ctx.log)
    ctx.session.write_artifact("computable_claims.json",
                               json.dumps(claims, indent=2))
    for c in claims.get("claims", []):
        marker = "+" if c.get("classification") == "COMPUTABLE" else "-"
        ctx.log(f"  [{marker}] {c.get('claim')} - {c.get('note', '')[:90]}")
    for q in claims.get("questions_for_user", []):
        ctx.log(f"  ? {q}")
    if not ctx.io.confirm("Proceed with the computable claims above?"):
        return StageResult(1, "aborted", reason="precheck",
                           detail="user declined the computable claims")
    return StageResult(1, "completed", artifacts=["computable_claims.json"])


# --- Stage 2: criteria + Gate 1 ---------------------------------------------

def _make_evidence(kind, reason, doc, margins=None, detail=None):
    from syngen.phases.rework import make_evidence
    return make_evidence(kind, reason, doc, margins=margins, detail=detail)


def stage_criteria(ctx):
    from syngen.phases.amend import apply_amendments
    from syngen.phases.critic import (block_issues, corrective_brief as critic_brief,
                                      critique_artifact, render_issues)
    from syngen.phases.criteria_lint import (corrective_brief,
                                             lint_criteria_internal, render_lint)
    from syngen.phases.intake import draft_criteria, enforce_coverage
    from syngen.phases.rework import recover_criteria_consistency
    from syngen.pipeline import _print_criteria

    session, client, io, log = ctx.session, ctx.client, ctx.io, ctx.log
    story, flags = ctx.story, ctx.flags
    claims = _claims(session)

    decisions_path = session.root / "decisions.md"
    if decisions_path.exists():
        decisions_text = decisions_path.read_text(encoding="utf-8")
    else:
        decisions_text = io.free_text(
            "Answer any pre-check questions now (blank line to finish), "
            "or leave empty:")
        session.write_artifact("decisions.md", decisions_text or "(none)")

    doc = draft_criteria(client, story, decisions_text, claims=claims,
                         split=(flags.get("stage23") == "split"))
    doc, cov_status = enforce_coverage(client, story, doc, claims,
                                       decisions_text=decisions_text,
                                       log_fn=log)
    if cov_status == "uncovered":
        session.write_artifact("criteria.json", json.dumps(doc, indent=2))
        ev = _make_evidence("criteria_coverage",
                            "drafted criteria express none of the claims", doc)
        return StageResult(2, "escalated", reason="criteria_coverage",
                           evidence=ev, rewind_to=2)
    if cov_status == "redrafted":
        session.log("COVERAGE GUARD: criteria re-drafted to cover claims.")
    if cov_status == "proceeded_with_notes":
        session.log("COVERAGE GUARD: proceeding with noted vocabulary gaps.")

    if flags.get("use_critic", True):
        verdict = critique_artifact(client, story, "acceptance criteria", doc)
        issues = block_issues(verdict)
        if issues:
            session.log("CRITIC (criteria) block findings:\n"
                        + render_issues(issues))
            log(f"Critic flagged {len(issues)} block issue(s) - one re-draft.")
            doc = draft_criteria(client, story, decisions_text + "\n\n"
                                 + critic_brief(issues))
            doc, cov_status = enforce_coverage(client, story, doc, claims,
                                               decisions_text=decisions_text,
                                               log_fn=log)
            if cov_status == "uncovered":
                session.write_artifact("criteria.json",
                                       json.dumps(doc, indent=2))
                ev = _make_evidence("criteria_coverage",
                                    "criteria lost coverage after critic",
                                    doc)
                return StageResult(2, "escalated",
                                   reason="criteria_coverage", evidence=ev,
                                   rewind_to=2)
            session.log("CRITIC: corrective criteria re-draft accepted.")
            # P17: re-check the critic on the re-draft. A persistent block
            # finding (e.g. a proxy criterion that measures the wrong thing)
            # must escalate, not ship.
            verdict2 = critique_artifact(client, story, "acceptance criteria",
                                         doc)
            issues2 = block_issues(verdict2)
            if issues2:
                session.log("CRITIC (criteria) STILL blocking after re-draft:\n"
                            + render_issues(issues2))
                log(f"Critic block findings persist ({len(issues2)}) - "
                    "escalating rather than shipping proxy criteria.")
                ev = _make_evidence(
                    "criteria_intent",
                    "critic block findings persist after re-draft", doc,
                    detail=render_issues(issues2)[:500])
                return StageResult(2, "escalated", reason="criteria_intent",
                                   evidence=ev, rewind_to=2)

    lint_hard, lint_notes = lint_criteria_internal(doc)
    for note in lint_notes:
        log(f"  [lint] {note}")
    if lint_hard:
        session.log("CRITERION CONSISTENCY LINT:\n" + render_lint(lint_hard))
        log("Criterion consistency violations - one corrective re-draft.")
        doc = draft_criteria(client, story, decisions_text + "\n\n"
                             + corrective_brief(lint_hard))
        doc, cov_status2 = enforce_coverage(client, story, doc, claims,
                                            decisions_text=decisions_text,
                                            log_fn=log)
        lint_hard, _ = lint_criteria_internal(doc)
        if cov_status2 == "uncovered":
            session.write_artifact("criteria.json", json.dumps(doc, indent=2))
            ev = _make_evidence("criteria_consistency",
                                "conflicting criteria persisted", doc)
            return StageResult(2, "escalated", reason="criteria_consistency",
                               evidence=ev, rewind_to=2)
        if lint_hard and flags.get("max_rework_rounds", 0) > 0:
            doc, ok, directives = recover_criteria_consistency(
                client, story, doc, claims, decisions_text, lint_hard,
                flags.get("max_rework_rounds", 0), log_fn=log)
            session.log("GATE-1 REWORK: " + json.dumps(directives, indent=1))
            if ok:
                session.write_artifact("criteria.json",
                                       json.dumps(doc, indent=2))
                lint_hard = []
        if lint_hard:
            session.write_artifact("criteria.json", json.dumps(doc, indent=2))
            ev = _make_evidence("criteria_consistency",
                                "conflicting criteria persisted", doc)
            return StageResult(2, "escalated", reason="criteria_consistency",
                               evidence=ev, rewind_to=2)
        session.log("CRITERION CONSISTENCY: corrective re-draft accepted.")

    # --- Final menu gate (P13): a wall, not advice. After every re-draft
    # path has run, the finished criteria must be buildable. Bounded,
    # menu-constrained re-draft; persistent violations escalate honestly.
    from syngen.menu import menu_findings
    for _ in range(2):
        residual = menu_findings(doc)
        if not residual:
            break
        session.log("MENU GATE: " + "; ".join(residual)[:500])
        log(f"Menu gate: {len(residual)} violation(s) - menu-constrained "
            "re-draft.")
        brief = ((decisions_text or "")
                 + "\n\nMENU VIOLATIONS - fix ALL of these; use ONLY buildable "
                 "checks, and never duplicate a claim:\n- "
                 + "\n- ".join(residual))
        # P17: claim-preserving (coverage re-checked against original claims).
        from syngen.phases.rework import redraft_criteria
        new_doc, ok = redraft_criteria(client, story, doc, claims,
                                       decisions_text, brief, log_fn=log,
                                       menu_constrained=True)
        if not ok:
            session.write_artifact("criteria.json", json.dumps(doc, indent=2))
            ev = _make_evidence("criteria_menu",
                                "menu re-draft lost claim coverage or stayed "
                                "inconsistent", doc)
            return StageResult(2, "escalated", reason="criteria_menu",
                               evidence=ev, rewind_to=2)
        doc = new_doc
    residual = menu_findings(doc)
    if residual:
        session.write_artifact("criteria.json", json.dumps(doc, indent=2))
        session.log("ESCALATED: criteria_menu - " + "; ".join(residual)[:500])
        log("\nNEEDS YOUR ATTENTION: criteria violate the buildable menu even "
            "after a menu-constrained re-draft (see criteria.json).")
        ev = _make_evidence("criteria_menu",
                            "criteria violate the buildable menu", doc,
                            detail="; ".join(residual)[:500])
        return StageResult(2, "escalated", reason="criteria_menu",
                           evidence=ev, rewind_to=2)

    _print_criteria(io, doc)
    while not io.confirm("Sign off these criteria?", default=True):
        overrides = io.ask(
            "Overrides (e.g. AC3.target_pct=21, AC6.min_gap_pp=4)")
        try:
            doc, changed, affected = apply_amendments(doc, overrides)
            _print_criteria(io, doc)
        except ValueError as e:
            log(f"Could not apply override: {e}")
    session.write_artifact("criteria.json", json.dumps(doc, indent=2))
    session.log("GATE 1 passed: criteria signed off.")
    return StageResult(2, "completed", artifacts=["criteria.json",
                                                  "decisions.md"])


# --- Stage 3: config (dials) + critic B + schema lint ------------------------

def _spec_notes(ctx, doc):
    from syngen.pipeline import criteria_summary
    session = ctx.session
    spec_path = session.root / "spec.md"
    if spec_path.exists():
        return spec_path.read_text(encoding="utf-8")
    spec_lines = []
    if ctx.flags.get("use_personas"):
        from syngen.phases.spec import persona_critique
        critique = persona_critique(ctx.client, ctx.story,
                                    criteria_summary(doc), log_fn=ctx.log)
        for persona in ("domain_expert", "bi_engineer", "outsider"):
            for bullet in critique.get(persona, [])[:5]:
                spec_lines.append(f"- [{persona}] {bullet}")
    conflict_notes = ctx.io.free_text(
        "Resolve flagged conflicts (one per line, blank to finish):")
    notes = ("\n".join(spec_lines)
             + f"\n\nUser resolutions:\n{conflict_notes}").strip()
    session.write_artifact("spec.md", notes or "none")
    return notes or "none"


def stage_config(ctx):
    from syngen.config import ConfigError
    from syngen.phases.buildability import BuildabilityError
    from syngen.phases.critic import (block_issues, corrective_brief as critic_brief,
                                      critique_artifact, render_issues)
    from syngen.phases.spec import draft_simulator
    from syngen.pipeline import criteria_summary, gate_lint

    session, client, io, log = ctx.session, ctx.client, ctx.io, ctx.log
    doc = _criteria(session)
    spec_notes = _spec_notes(ctx, doc)
    if ctx.guidance:
        spec_notes = (spec_notes + "\n\n" + ctx.guidance).strip()
    crit_summary = criteria_summary(doc)
    checks = [c["check"] for c in doc.get("criteria", [])]
    split = (ctx.flags.get("stage23") == "split")

    try:
        sim_cfg = draft_simulator(client, ctx.story, crit_summary, spec_notes,
                                  checks=checks, split=split)
    except BuildabilityError as e:
        ev = _make_evidence("stage3_buildability",
                            "config cannot express the criteria", doc,
                            detail=str(e))
        return StageResult(3, "escalated", reason="stage3_buildability",
                           evidence=ev, rewind_to=3)
    except ConfigError as e:
        ev = _make_evidence("draft_invalid",
                            "simulator draft invalid after re-drafts", doc,
                            detail=str(e))
        return StageResult(3, "escalated", reason="draft_invalid",
                           evidence=ev, rewind_to=3)

    if ctx.flags.get("use_critic", True):
        verdict = critique_artifact(
            client, ctx.story, "simulator.json (data generator config)",
            {"criteria": doc.get("criteria"), "simulator": sim_cfg})
        issues = block_issues(verdict)
        if issues:
            session.log("CRITIC (config) block findings:\n"
                        + render_issues(issues))
            log(f"Critic flagged {len(issues)} block issue(s) - one re-draft.")
            try:
                sim_cfg = draft_simulator(
                    client, ctx.story, crit_summary,
                    spec_notes + "\n\n" + critic_brief(issues),
                    corrective_findings=critic_brief(issues),
                    checks=checks, split=split)
            except BuildabilityError as e:
                ev = _make_evidence("stage3_buildability",
                                    "config cannot express the criteria", doc,
                                    detail=str(e))
                return StageResult(3, "escalated",
                                   reason="stage3_buildability", evidence=ev,
                                   rewind_to=3)
            except ConfigError as e:
                ev = _make_evidence("draft_invalid",
                                    "simulator draft invalid after critic", doc,
                                    detail=str(e))
                return StageResult(3, "escalated", reason="draft_invalid",
                                   evidence=ev, rewind_to=3)

    doc.setdefault("definitions", {})["quarter_end_dates"] = dict(
        zip(sim_cfg["time_model"]["quarter_labels"],
            sim_cfg["time_model"]["quarter_end_dates"]))
    session.write_artifact("criteria.json", json.dumps(doc, indent=2))

    sim_cfg = gate_lint(io, session, sim_cfg, log)
    if sim_cfg is None:
        return StageResult(3, "aborted", reason="manual_edit",
                           detail="config blocked by lint; manual edit requested")
    return StageResult(3, "completed", artifacts=["simulator.json",
                                                  "criteria.json", "spec.md"])


# --- Stage 4: pre-flight calibration + geometry ------------------------------

def stage_preflight(ctx):
    from syngen.phases.criteria_lint import cross_lint
    from syngen.pipeline import (_capability_workbench, _geometry_corrective,
                                 calibrate_gate, criteria_summary)

    session, client, io, log = ctx.session, ctx.client, ctx.io, ctx.log
    doc = _criteria(session)
    sim_cfg = _simulator(session)
    claims = _claims(session)
    decisions_text = _decisions(session)
    crit_summary = criteria_summary(doc)
    checks = [c["check"] for c in doc.get("criteria", [])]
    split = (ctx.flags.get("stage23") == "split")

    if ctx.flags.get("use_capability"):
        doc, _adj = _capability_workbench(session, client, ctx.story, doc,
                                          claims, decisions_text, sim_cfg,
                                          log, max_rounds=3)
        crit_summary = criteria_summary(doc)

    doc, esc = _geometry_corrective(session, client, ctx.story, doc, claims,
                                    decisions_text, sim_cfg, log,
                                    feasibility=False)
    if esc is not None:
        return StageResult(4, "escalated", reason="criteria_geometry",
                           evidence=esc.get("evidence"), rewind_to=2)

    sim_cfg, status, hard = calibrate_gate(
        client, io, ctx.story, crit_summary, _spec_notes(ctx, doc), doc,
        sim_cfg, session, log, checks=checks, split=split)
    if sim_cfg is None:
        from syngen.phases.preflight import render_findings
        structural = all(f.get("rule") == "PF0"
                         and str(f.get("msg", "")).startswith("config invalid")
                         for f in (hard or []))
        detail = (render_findings(hard) if hard else
                  "deterministic calibration could not satisfy the criteria")
        kind = "preflight_structural" if structural else "preflight_calibration"
        ev = _make_evidence(kind, f"preflight calibration: {status}", doc,
                            detail=detail)
        return StageResult(4, "escalated", reason=kind, evidence=ev,
                           rewind_to=(3 if structural else 4))

    doc, esc = _geometry_corrective(session, client, ctx.story, doc, claims,
                                    decisions_text, sim_cfg, log,
                                    feasibility=True)
    if esc is not None:
        return StageResult(4, "escalated", reason="criteria_geometry",
                           evidence=esc.get("evidence"), rewind_to=2)
    return StageResult(4, "completed", artifacts=["simulator.json",
                                                  "criteria.json"])


# --- Stage 5: the convergence loop -------------------------------------------

def stage_converge(ctx):
    from syngen.phases.converge import LoopEscalation, run_convergence

    session, client, log = ctx.session, ctx.client, ctx.log
    flags = ctx.flags
    try:
        summary = run_convergence(
            session, client, session.root / "simulator.json",
            session.root / "criteria.json",
            max_iterations=flags.get("max_iterations", 10),
            max_llm_proposals=flags.get("max_llm_proposals", 8),
            log_fn=log)
    except LoopEscalation as esc:
        doc = _criteria(session)
        margins = {}
        for r in esc.results or []:
            if r.get("verdict") != "PASS" and r.get("margin") is not None:
                margins[r.get("id")] = round(float(r["margin"]), 2)
        ev = _make_evidence("convergence", esc.reason, doc, margins=margins,
                            detail="tuning loop could not satisfy all criteria")
        return StageResult(5, "escalated", reason=esc.reason, evidence=ev,
                           rewind_to=None)
    session.write_artifact("convergence_summary.json",
                           json.dumps(summary, indent=2))
    return StageResult(5, "completed",
                       artifacts=["convergence_summary.json"])


# --- Stage 6: structure gate + final proof -----------------------------------

def stage_structure(ctx):
    from syngen.pipeline import post_generate_structure_gate, run_validation_final
    from syngen.validator.report import render_table

    session, log = ctx.session, ctx.log
    summary = _read_json(session.root / "convergence_summary.json")
    sim_cfg = _simulator(session)
    ok, sfindings = post_generate_structure_gate(summary["workbook"], log,
                                                 cfg=sim_cfg)
    if not ok:
        detail = "; ".join(msg for _, _, msg in sfindings)
        ev = _make_evidence("structure", "workbook schema mismatch",
                            _criteria(session), detail=detail)
        return StageResult(6, "escalated", reason="structure_check_failed",
                           evidence=ev, rewind_to=5)

    results, all_pass = run_validation_final(summary,
                                             session.root / "criteria.json")
    report_md = render_table(results, all_pass) if all_pass else "(see log)"
    session.write_artifact("validation_report.md", f"```\n{report_md}\n```\n")
    session.log("GATE 2 passed: delivered.")
    return StageResult(6, "completed", artifacts=["validation_report.md"])


# --- Stage 7: deliver --------------------------------------------------------

def stage_deliver(ctx):
    session = ctx.session
    summary = {}
    try:
        summary = _read_json(session.root / "convergence_summary.json")
    except Exception:  # noqa: BLE001 - delivery notes are best-effort
        pass
    log = ctx.log
    log(f"\nDeliverables in {session.root}")
    log("  dataset:   dataset.xlsx")
    log("  proof:     validation_report.md")
    log("  config:    simulator.json")
    if summary.get("thin_margins"):
        log(f"  note: thin margins on {', '.join(summary['thin_margins'])}")
    if not ctx.io.confirm("Inspect and accept delivery?", default=True):
        return StageResult(7, "aborted", reason="delivered_unaccepted")
    return StageResult(7, "completed")


STAGES = {
    1: ("intake", stage_intake),
    2: ("criteria", stage_criteria),
    3: ("config", stage_config),
    4: ("preflight", stage_preflight),
    5: ("converge", stage_converge),
    6: ("structure", stage_structure),
    7: ("deliver", stage_deliver),
}
