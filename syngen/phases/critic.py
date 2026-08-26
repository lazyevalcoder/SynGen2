"""P5 WP9: the critic agent in the drafter/critic multi-agent pair.

The drafter (decompose/simulator_draft) produces artifacts; the critic
reviews them for INTENT errors - dropped claims, direction inversions,
implausible magnitudes - that deterministic linters cannot see. Verdicts
are structured JSON; block-severity findings trigger exactly one
corrective re-draft through the existing redraft paths. The critic adds
at most two LLM calls per flight and is default-on in the fly pipeline.
"""
import json

from syngen.phases.json_task import chat_json
from syngen.prompts import load_prompt


def critique_artifact(client, story, artifact_kind, payload):
    """Run one critic pass. Returns the parsed verdict dict, or None when
    the critic itself fails (critic failure never kills a flight)."""
    system = load_prompt(
        "critic",
        story=story,
        artifact_kind=artifact_kind,
        payload=payload if isinstance(payload, str)
        else json.dumps(payload, indent=2)[:6000],
    )
    try:
        return chat_json(client, "critic", system,
                         "Produce the critic verdict now.")
    except Exception:  # noqa: BLE001 - critic must fail open
        return None


def block_issues(verdict):
    """Block-severity issues from a verdict dict (empty if clean/None)."""
    if not isinstance(verdict, dict):
        return []
    out = []
    for issue in verdict.get("issues", []):
        if isinstance(issue, dict) and issue.get("severity") == "block":
            out.append(issue)
    return out


def render_issues(issues):
    lines = []
    for i in issues:
        lines.append(f"  - [{i.get('id', 'general')}] {i.get('issue', '')}"
                     + (f" -> {i['suggestion']}" if i.get("suggestion")
                        else ""))
    return "\n".join(lines)


def corrective_brief(issues):
    return ("CRITIC FINDINGS - the draft misrepresents the story. Fix ALL "
            "of these:\n"
            + "\n".join(f"- [{i.get('id', 'general')}] {i.get('issue', '')}"
                        + (f" Suggestion: {i['suggestion']}"
                           if i.get("suggestion") else "")
                        for i in issues))
