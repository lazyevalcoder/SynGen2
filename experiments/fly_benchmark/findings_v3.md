# Fly Benchmark Findings v3 — Fresh-Cohort Verification (scenarios 11–15)

> **Purpose:** P5's flight-control envelope was designed from the failure
> taxonomy of scenarios 01–10 (see `findings_v2.md`). Before resuming the
> full certification sweep, we fly scenarios 11–15 — never seen during
> design — to verify the fixes generalize beyond their derivation set.
>
> **Code line:** `6d91bdc` (P5 complete). Protocol unchanged: one scenario
> per batch, diagnosis logged before the next flight, no mid-run fixes.

## Scoreboard (this file)

| Scenario | Outcome | Iterations | Elapsed | Escalation reason |
|---|---|---|---|---|
| 11 | **LANDED** | 1 | 670s | - |

---

## Batch 11 (2026-08-26) — scenario_11 · LANDED ✅ (iteration 1, 8/8, 0 LLM proposals)

Fresh-cohort first flight: never seen during P5 design. The pipeline
coverage-decay story exercised stage-history aging, slippage trends, and
quota-relative coverage — machinery barely touched by scenarios 01–10.

### Outcome
Converged on iteration 1 with every knob solved deterministically
(`llm_proposals: 0`) — the Autopilot carried the entire convergence.

### Observations (P5 generalization evidence)
1. **Critic A engaged**: blocked 3 issues in drafted criteria → one
   corrective re-draft (WP9 verification point 1, firing on fresh material).
2. **Critic B engaged**: blocked 6 issues in config draft → one corrective
   re-draft (verification point 2), incl. a taxonomy ADVISE lint.
3. **PF0 input-hardening path worked end-to-end**: first calibration
   produced `share_open_by_quarter` = 0.9691 > 0.95 cap → ConfigError →
   PF0 HARD finding → bounded re-draft → second calibration clean
   (`[0.0879..0.6812]`, predicted stale 51%). This is the F12.1 crash
   class converted into a routine self-heal — on a scenario the fix was
   never designed against.
4. **Autopilot breadth on unseen ground**: slippage path solved (+22pp vs
   ≥10pp requirement), deal durations shortened when the staleness cap was
   unreachable at drafted cycle length ("the staleness cap was unreachable
   at the drafted cycle length"), per-quarter plan rescaling for all three
   coverage criteria.

### Candidate finding (non-fatal, logged only)
- **F19.1 (fidelity, landed-anyway): directional endpoint semantics.**
  Story asserts coverage *fell* 4.1x → 3.0x; dataset shows 4.61x → 4.67x
  (a rise). Both endpoint criteria use `coverage_ratio` floor semantics
  (≥4.1 / ≥3.0), which cannot express "declined TO 3.0" — a ceiling/band
  parameter class is missing. The graduated guard correctly routed the
  relational claim ("effective < reported") to notes (vocabulary gap),
  and Gate 1 signed the floors anyway. Flight is valid per its signed
  contract, but story-direction fidelity is weaker than the verdict
  table suggests. → vocabulary queue, not a flight failure.

