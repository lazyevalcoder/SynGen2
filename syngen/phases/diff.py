"""Story-diff classification: route tweaks as parametric / taxonomy / structural.

The LLM proposes a route; deterministic guardrails validate it. If the
proposed edits don't fit the claimed route, we escalate to structural rather
than trusting the classification (GAPS G11: routing errors are the failure
mode, so the router itself gets checked).
"""
import re

from syngen.phases.json_task import chat_json
from syngen.prompts import load_prompt

ROUTES = ("parametric", "taxonomy", "structural")

# Config containers that hold categorical value sets (taxonomy edits live here).
TAXONOMY_PATHS = (
    re.compile(r"^accounts\.(regions|segments|industries)(\..*)?$"),
    re.compile(r"^accounts\.industries(\[\d+\])?$"),
    re.compile(r"^opportunities\.owners(\[\d+\])?$"),
)


class RoutingError(ValueError):
    pass


def classify_story_change(client, old_story, new_story, criteria_summary,
                          sim_summary, log_fn=print):
    system = load_prompt(
        "story_diff",
        old_story=old_story[:2000],
        new_story=new_story[:2000],
        criteria=criteria_summary,
        simulator=sim_summary,
    )
    result = chat_json(client, "story_diff", system,
                       "Classify this story change now.")
    route = str(result.get("route", "")).lower().strip()
    if route not in ROUTES:
        raise RoutingError(f"classifier returned unknown route: {route!r}")
    log_fn(f"Diff classifier: route={route} "
           f"({len(result.get('changed_claims', []))} changed claim(s))")
    return result


def validate_route(route_result, criteria_ids):
    """Deterministic check that proposed edits match the claimed route.

    - taxonomy: every config edit must target a categorical value container;
      criteria amendments are not allowed.
    - parametric: only criteria param amendments allowed; config edits must
      be absent.
    - structural: always accepted (escalation path).

    Raises RoutingError when the proposal contradicts its own route.
    """
    route = route_result.get("route")
    config_edits = route_result.get("proposed_config_edits", []) or []
    amendments = route_result.get("proposed_criteria_amendments", []) or []

    if route == "structural":
        return route_result

    for ch in config_edits:
        if not isinstance(ch, dict) or not ch.get("path"):
            raise RoutingError("malformed config edit in proposal")
        if route == "parametric":
            raise RoutingError(
                f"route=parametric but proposes config edit {ch['path']}")
        if route == "taxonomy" and not any(
                p.match(ch["path"]) for p in TAXONOMY_PATHS):
            raise RoutingError(
                f"route=taxonomy but '{ch['path']}' is not a categorical "
                "value container; treating as structural")

    for am in amendments:
        cid = str(am.get("id", "")).strip()
        if cid and cid not in criteria_ids:
            raise RoutingError(f"amendment references unknown criterion {cid}")
        if route == "taxonomy" and cid:
            raise RoutingError(
                "route=taxonomy must not amend acceptance criteria")

    if route == "taxonomy" and not config_edits:
        raise RoutingError("route=taxonomy without any config edit")
    return route_result
