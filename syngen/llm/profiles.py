"""Evidence-based per-task token budgets and reasoning controls.

Parameter support on llama.cpp b10472 + Ornith-1.5-35B (measured live):
- reasoning_effort: IGNORED by llama.cpp (kept only for OpenAI endpoints)
- enable_thinking=False via chat_template_kwargs: VERIFIED working
- reasoning_budget_tokens=N: VERIFIED working - hard cap on thinking tokens
  (probe: budget=50 cut reasoning from 3,078 to 272 chars, elapsed halved)

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
}


def profile_for(task):
    if task not in PROFILES:
        raise KeyError(f"unknown task profile: {task}. Known: {sorted(PROFILES)}")
    return dict(PROFILES[task])
