"""Evidence-based per-task token budgets and reasoning efforts.

Measured on Ornith-1.5-35B Q4_K_M (see docs/PERFORMANCE_EXPECTATIONS.md):
max_tokens is a CEILING not a target - unused budget costs nothing, but
oversized ceilings combined with empty-content retries cost ~10 min/attempt.
"""
PROFILES = {
    # genuinely needs thinking: observed 3,495 tokens total, finish=stop
    "decompose": {"max_tokens": 8192, "reasoning_effort": "medium"},
    # mechanical JSON tasks: outputs typically 400-1,500 tokens
    "precheck": {"max_tokens": 4096, "reasoning_effort": "low"},
    "personas": {"max_tokens": 4096, "reasoning_effort": "low"},
    "simulator_draft": {"max_tokens": 4096, "reasoning_effort": "low"},
    "knob_proposal": {"max_tokens": 4096, "reasoning_effort": "low"},
}


def profile_for(task):
    if task not in PROFILES:
        raise KeyError(f"unknown task profile: {task}. Known: {sorted(PROFILES)}")
    return dict(PROFILES[task])


def chat_task(client, task, system, user, log_fn=None):
    """Send a chat completion using the task's evidence-based profile."""
    p = profile_for(task)
    return client.chat(system, user, max_tokens=p["max_tokens"],
                       reasoning_effort=p["reasoning_effort"])
