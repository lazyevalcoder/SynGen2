"""Evidence-based per-task token budgets and reasoning controls.

Parameter support on the llama.cpp server (`/v1/chat/completions`):
- enable_thinking via chat_template_kwargs: VERIFIED working (per-request).
- reasoning_effort: a DOCUMENTED per-request field - "none" disables
  reasoning, other levels are passed to the jinja template. (An older note
  here claimed llama.cpp ignores it; that was wrong.)
- reasoning_budget_tokens: NOT a documented request field. The thinking
  token budget is a SERVER flag (llama-server --reasoning-budget N, env
  LLAMA_ARG_THINK_BUDGET). The per-task reasoning_budget_tokens below are
  therefore advisory only on current llama.cpp - rely on enable_thinking and
  the server-side cap.
- response_format (json_object / json_schema): supported per-request.

max_tokens is a CEILING not a target - but ceilings below the model's natural
verbosity truncate JSON mid-array and produce parse failures, so give
headroom (personas was truncated at 4096; raised to 6144 + brevity prompt).
"""
PROFILES = {
    # language reasoning where thinking earns its keep; observed ~3.5k total
    "decompose": {"max_tokens": 8192, "enable_thinking": True,
                  "reasoning_budget_tokens": 4000},
    # mechanical JSON tasks - minimal thinking, verified fast and parseable
    "precheck": {"max_tokens": 6144, "enable_thinking": False},
    "personas": {"max_tokens": 6144, "enable_thinking": False},
    # calibration task: worked example in its prompt carries the math;
    # a small thinking budget lets it check numbers without runaway
    "simulator_draft": {"max_tokens": 8192, "reasoning_budget_tokens": 400,
                        "max_attempts": 2},
    "knob_proposal": {"max_tokens": 8192, "reasoning_budget_tokens": 400,
                      "max_attempts": 2},
    # routing decision: small structured output; deterministic guardrails
    # double-check the route, so thinking is unnecessary
    "story_diff": {"max_tokens": 4096, "enable_thinking": False},
    # coverage audit: strictness over depth - short verdict per claim;
    # a parse failure here fails OPEN (guard degrades to deterministic
    # rules) rather than blocking the session
    "coverage_audit": {"max_tokens": 4096, "enable_thinking": False},
    # P5 critic (WP9): adversarial intent review of drafted artifacts;
    # structured verdict, no thinking needed - same shape as coverage_audit.
    # A critic failure fails OPEN (flight proceeds without critique).
    "critic": {"max_tokens": 4096, "enable_thinking": False},
    # rework judge: reads escalation evidence and routes the next attempt
    # (criteria / config / escalate). Deterministic guardrails re-check the
    # route, so a routing error is cheap and survivable.
    "rework_judge": {"max_tokens": 4096, "enable_thinking": False},
}


def profile_for(task):
    if task not in PROFILES:
        raise KeyError(f"unknown task profile: {task}. Known: {sorted(PROFILES)}")
    return dict(PROFILES[task])
