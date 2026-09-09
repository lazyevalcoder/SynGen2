# SynGen Performance Expectations

> **Status:** v1 - measured on llama.cpp b10472 (win-cuda-12.4) with Ornith-1.5-35B-Q4_K_M on a single-slot local server. Numbers are from live sessions August 2026; expect variance with different models/hardware.

---

## What a user should expect

| Scenario | Typical wall time |
|----------|------------------|
| Full session, story lands in 1-3 iterations | **2 - 5 minutes** |
| Session needing more convergence work | 5 - 10 minutes |
| Escalation (loop cap hit, needs your attention) | ~10 minutes, then stops cleanly - never hangs |
| Any single LLM call | 15 - 120 seconds |

An LLM call is never instant. A session that finishes in under two minutes is running well; if anything appears "stuck" for more than ~3 minutes without log output, it likely has - see Known Issues below.

## Measured per-task latency (live)

| Task | Latency | Tokens | Notes |
|------|---------|--------|-------|
| precheck | ~47s / faster with no-think | 500-1,100 | |
| decompose | ~95s | ~4,500 | only task where thinking stays ON |
| personas | ~26-60s | 700-1,200 | brevity-constrained (max 3 bullets/persona) |
| simulator_draft | 15-123s | 569-5,800 | was the worst offender pre-fixes |
| knob_proposal | 30-200s | varies with history | |

Full-session wall time is dominated by the convergence loop (one generation pass is fast; each LLM proposal adds 0.5-3 minutes).

## LLM parameter support (llama.cpp b10472 + Ornith-1.5-35B)

**Verified empirically, not assumed:**

| Parameter | Supported? | Evidence |
|-----------|-----------|----------|
| `reasoning_effort` (low/medium/high) | **NO** - silently ignored | low vs baseline: identical behavior (27s vs 26s, same reasoning volume) |
| `chat_template_kwargs {"enable_thinking": false}` | **YES** | thinking-off call: 15.3s / 569 tokens vs 356s / 16,384 wasted with thinking on |
| `reasoning_budget_tokens: N` | **YES** | budget=50 cut reasoning 3,078 -> 272 chars, elapsed halved |

SynGen therefore uses `enable_thinking` and `reasoning_budget_tokens` exclusively. `reasoning_effort` remains in the client only for future OpenAI-compatible endpoints that honor it.

## Failure modes we guard against (and their costs)

1. **Reasoning burnout**: model spends entire token budget thinking, returns empty content. Guard: `reasoning_budget_tokens` caps + retry ceiling at 16k. Cost before fix: ~6 min/call wasted.
2. **JSON truncation**: verbose output cut mid-array by the token ceiling. Guard: brevity prompts + truncation-aware retries that RAISE the budget (re-asking at the same ceiling fails identically).
3. **Malformed JSON**: stochastic bad sample. Guard: corrective re-ask quoting the bad output (usually recovers in 1 extra call).
4. **Console encoding crashes**: LLM text contains unicode beyond cp1252. Guard: safe-print fallback.

## Operational notes

- Single-slot server: one slow/orphaned request blocks everything behind it. If a call seems hung, check whether a previous client disconnected mid-generation; restart the server to clear it.
- `--parallel N` (if RAM allows) prevents queue-blocked states.
- Determinism applies to GENERATION (same seed + config = same data), not to LLM calls - criteria/knob proposals vary run to run.
