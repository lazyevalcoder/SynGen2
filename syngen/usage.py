"""Per-flight LLM usage capture (P15).

The client accumulates call/token totals; this writes them to the session so
cost is auditable - the `new`/`run` path previously discarded them (only
`fly` reported usage).
"""
import json


def usage_totals(client):
    return client.usage_totals() if hasattr(client, "usage_totals") else {}


def write_usage(session, client):
    u = usage_totals(client)
    try:
        session.write_artifact("usage.json", json.dumps(u, indent=2))
    except Exception:  # noqa: BLE001 - usage capture must never break a flight
        pass
    return u


def render_usage(u):
    if not u:
        return "LLM usage: (none recorded)"
    return (f"LLM usage: {u.get('calls', 0)} calls, "
            f"{u.get('total_tokens', 0):,} tokens "
            f"(prompt {u.get('prompt_tokens', 0):,} / completion "
            f"{u.get('completion_tokens', 0):,}), "
            f"{u.get('elapsed_s', 0)}s")
