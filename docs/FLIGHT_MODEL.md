# The Flight Model — SynGen's Autonomy Doctrine

*Written 2026-08-25 (M5 iteration 5). This is the design lens every roadmap
item is now evaluated against.*

## The analogy

SynGen is an **aircraft**; the local LLM is its **pilot**; we are the
**aircraft makers**. The pilot is a competent professional: given a sound
airframe, clear instruments, and good training, they fly the mission
alone. The maker's job is not to ride along and grab the yoke at the first
turbulence — it is to build an aircraft that recovers on its own, and to
make sure that when the pilot *does* call in a problem, the report tells
maintenance exactly which system failed.

The v1 scorecard says 25/25 scenarios landed. The honest reading of how:
on many flights an instructor's hands were on the controls (hand-edited
session files). Iteration 5 onward exists to remove those hands.

## The control hierarchy

| Layer | Aviation | In SynGen | Status |
|---|---|---|---|
| Airframe & instruments | Structure, gauges | Fixed declarative engine, black-box validator, session store | ✅ stable contracts |
| Pilot training | Simulator hours | Prompt vocabulary, worked examples, check catalogs with triggers | ✅ iter 5 |
| Envelope protection | Limits the aircraft enforces | Schema linter, pre-flight HARD referential findings, coverage guard, criteria coherence rules | ✅ iters 3–5 |
| Auto-throttle | Engine manages power automatically | Deterministic auto-calibration solvers (levels, tier mix, attainment, capacity ramping, whale sizing) | ✅ iters 3–5 |
| **Autopilot / stall recovery** | Detects deviation, corrects, retries without help | In-loop deterministic remedies before any LLM spend: one re-calibration pass (heals omitted-block structural failures), one bounded seed bump on draw-noise, early stall escalation with worst margins named | ✅ iter 5 |
| Solo certification | Type rating, check rides | `syngen fly` / `run_fly`: fully non-interactive story→dataset→proof with telemetry (`fly_report.json`); `scripts/benchmark_fly.py` computes the unassisted landing rate | ✅ harness built; live benchmark pending go-ahead |
| Maintenance loop | Fleet data feeds redesigns | Escalations + telemetry convert into general primitives/solvers/guards (the defect-ledger discipline) | ✅ ongoing |

## Doctrines

1. **Human-on-exception, never human-in-the-loop.** A person reviews
   criteria before generation (Gate 1) and accepts delivery (Gate 2).
   Between the gates, no human input is required — including recovery
   from bad drafts. If we find ourselves hand-editing a session file,
   that is a defect against this doctrine and must be converted into a
   solver, guard, or prompt rule.
2. **Escalation = declared capability ceiling, nothing else.** The system
   must exhaust its own remedies first, and an escalation report must say
   precisely which claims could not be expressed or satisfied and why.
   "Escalated because automation was missing" is treated the same way
   aviation treats a crash: investigate, then change the aircraft so
   that class of event cannot recur.
3. **Honest emergency declaration.** A pilot who cannot land declares an
   emergency rather than faking a landing. SynGen refuses to deliver
   quietly-wrong data. This behavior is a feature to preserve, not a
   failure rate to suppress.
4. **Every intervention becomes permanent infrastructure.** Same rule as
   the defect ledger: any manual fix during development ships as a
   general mechanism, so the next flight needs nobody on board.

## Success metrics (replace "scenarios landed")

- **Unassisted landing rate**: % of fresh stories that reach delivered
  proof through `syngen fly` with zero human edits between gates.
- **Escalations per 10 stories**, each with a classified root cause.
- **Interventions per landing**: count of manual session-file edits made
  by builders. Target: zero, by construction.
