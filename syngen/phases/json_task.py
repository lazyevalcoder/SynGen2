"""Resilient JSON task execution: parse failures get corrective re-asks,
truncation gets a bigger budget (they are different failures with different fixes).
"""
from syngen.llm.profiles import profile_for
from syngen.utils import extract_json

MAX_TOKEN_CEILING = 16384


def chat_json(client, task, system, user, max_parse_attempts=3):
    """Run a task expecting a JSON object back, managing retries itself.

    - finish_reason=length (truncated JSON): raise the token ceiling - the
      model was mid-answer, not wrong. Re-asking with the same ceiling fails
      identically.
    - otherwise unparseable: corrective re-ask quoting the bad output.

    Live evidence: personas at a 4096 ceiling truncated mid-array ~1-in-2;
    identical re-asks could never recover.
    """
    profile = profile_for(task)
    tokens = profile["max_tokens"]
    last_content = ""
    last_finish = ""

    for attempt in range(1, max_parse_attempts + 1):
        response = client.chat(
            system, user, max_tokens=tokens,
            enable_thinking=profile.get("enable_thinking"),
            reasoning_budget_tokens=profile.get("reasoning_budget_tokens"),
            max_attempts=1,
        )
        last_content = response.content
        last_finish = response.finish_reason
        try:
            return extract_json(last_content)
        except ValueError:
            if attempt >= max_parse_attempts:
                break
            if response.finish_reason == "length":
                tokens = min(tokens * 2, MAX_TOKEN_CEILING)
                user = f"{user}\n\n(Be concise; complete the full JSON object.)"
            else:
                user = (
                    f"{user}\n\nYour previous reply was not parsable as a JSON "
                    f"object (it began: {last_content[:120]!r}). "
                    f"Reply again with ONLY the valid JSON object."
                )

    raise ValueError(
        f"{task}: no parsable JSON after {max_parse_attempts} attempts "
        f"(last finish={last_finish}); content began: {last_content[:200]!r}"
    )
