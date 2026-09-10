"""Criteria-stage probe (P10 step 2).

Skills (P9.1) affects only the criteria drafter; the long pole in a flight is
the convergence loop (stage 5). The probe runs stages 1-2 and, optionally,
drafts a config and runs the deterministic calibration + geometry lint - then
STOPS. It never runs the tuning loop, so a skills A/B is minutes, not
20-minute flights.

Outcome = did the draft survive the deterministic gates, plus the error
classes the guide targets (unknown check, vacuous threshold, pseudo-unit,
unreachable target).
"""
from syngen.phases.criteria_lint import cross_lint, lint_criteria_internal
from syngen.phases.critic import block_issues, critique_artifact, render_issues
from syngen.phases.intake import (draft_criteria, enforce_coverage,
                                  precheck_claims)


def _silent(*_a, **_k):
    pass


def probe_criteria(client, story, use_skills=True, use_critic=True,
                   with_config=False, log_fn=_silent):
    """Run stages 1-2 (+ optional 3-4) and report gate survival.

    Returns a dict with: coverage, gate1_pass, lint_hard, lint_notes,
    critic_blocks, n_criteria, checks, and - when with_config - the
    deterministic calibration + geometry findings and reachable_pass.
    Also carries the probe's llm_usage.
    """
    claims = precheck_claims(client, story, log_fn=log_fn)
    doc = draft_criteria(client, story, "", log_fn=log_fn,
                         use_skills=use_skills)
    doc, cov = enforce_coverage(client, story, doc, claims,
                                decisions_text="", log_fn=log_fn)

    critic_blocks = []
    if use_critic:
        verdict = critique_artifact(client, story, "acceptance criteria", doc)
        critic_blocks = [render_issues([i]) for i in block_issues(verdict)]

    hard, notes = lint_criteria_internal(doc)
    result = {
        "coverage": cov,
        "gate1_pass": cov != "uncovered" and not hard,
        "lint_hard": hard,
        "lint_notes": notes,
        "critic_blocks": critic_blocks,
        "n_criteria": len(doc.get("criteria", [])),
        "checks": sorted({c.get("check") for c in doc.get("criteria", [])}),
    }

    if with_config:
        from syngen.phases.preflight import (autocalibrate, calibrate,
                                             hard_findings)
        from syngen.phases.spec import draft_simulator
        from syngen.pipeline import criteria_summary

        sim = draft_simulator(client, story, criteria_summary(doc), "",
                              log_fn=log_fn)
        try:
            autocalibrate(sim, doc)
            cal_hard = hard_findings(calibrate(sim, doc))
        except Exception as e:  # noqa: BLE001 - probe must always report
            cal_hard = [{"rule": "probe", "severity": "HARD",
                         "msg": f"{type(e).__name__}: {e}"}]
        geo = cross_lint(sim, doc)
        result["calibration_hard"] = cal_hard
        result["geometry_findings"] = geo
        result["reachable_pass"] = not cal_hard and not geo

    result["llm_usage"] = (client.usage_totals()
                           if hasattr(client, "usage_totals") else {})
    return result
