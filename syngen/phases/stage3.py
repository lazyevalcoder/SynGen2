"""Stage 3, split: draft the config block by block, assemble in code (P11).

The classic stage 3 asks one 15.7k-char prompt for the whole simulator.json.
Here each artifact piece gets a small focused prompt; deterministic code
merges, normalizes and validates. The rule that keeps it from re-bloating:
LLM writes small pieces, code consolidates.

Requires `checks` (the criteria's check names) so the menu can decide which
optional blocks are actually needed.
"""
import json

from syngen.config import ConfigError, validate_simulator_doc
from syngen.phases.json_task import chat_json
from syngen.prompts import load_prompt

DEFAULT_TIME_MODEL = {
    "fiscal_year": "FY26",
    "quarter_labels": ["FY26-Q1", "FY26-Q2", "FY26-Q3", "FY26-Q4"],
    "quarter_end_dates": ["2026-03-31", "2026-06-30", "2026-09-30",
                          "2026-12-31"],
}
DEFAULT_OUTPUT = {"workbook": "output/dataset.xlsx"}
DEFAULT_SEED = 42
OPTIONAL_BLOCKS = ("products", "pipeline", "quota", "capacity", "ownership",
                   "activity", "forecast", "pricing_response")


def _tax():
    from syngen.phases.intake import _pack_taxonomy
    return _pack_taxonomy()


def _facts(checks):
    try:
        return _tax().check_facts(checks) or "(none registered)"
    except Exception:  # noqa: BLE001 - facts are advisory context
        return "(unavailable)"


def _render(name, story, criteria_summary, checks, spec_notes):
    from syngen.menu import required_blocks, required_features
    return load_prompt(
        f"blocks/{name}",
        story=story[:2000],
        criteria=criteria_summary,
        spec=(spec_notes or "none")[-1500:],
        check_facts=_facts(checks),
        required_blocks=", ".join(sorted(required_blocks(checks))) or "none",
        required_features=", ".join(sorted(required_features(checks))) or "none",
    )


def draft_core(client, story, criteria_summary, checks, spec_notes="",
               log_fn=print, corrective=""):
    """Draft the always-present blocks: accounts + opportunities."""
    system = _render("core", story, criteria_summary, checks, spec_notes)
    if corrective:
        system += ("\n\nCORRECTIVE FINDINGS - your previous assembly was "
                   "invalid; fix ALL of these:\n" + corrective)
    result = chat_json(client, "simulator_core", system,
                       "Produce the core JSON now.")
    if not isinstance(result, dict):
        raise ConfigError("stage-3 core draft is not a JSON object")
    return {"accounts": result.get("accounts") or {},
            "opportunities": result.get("opportunities") or {}}


def draft_block(client, block, story, criteria_summary, checks,
                spec_notes="", log_fn=print):
    """Draft one optional block; None means the block was omitted/failed."""
    system = _render(block, story, criteria_summary, checks, spec_notes)
    result = chat_json(client, f"simulator_{block}", system,
                       "Produce the block JSON now.")
    part = result.get(block) if isinstance(result, dict) else None
    return part if isinstance(part, dict) else None


def _normalize(cfg):
    """Deterministic consolidation fixes (shared with the classic path)."""
    from syngen.phases.preflight import (_normalize_capacity_headcounts,
                                         _normalize_quota_keys,
                                         _renormalize_product_shares_cfg)
    for fn in (_renormalize_product_shares_cfg, _normalize_quota_keys,
               _normalize_capacity_headcounts):
        try:
            fn(cfg)
        except Exception:  # noqa: BLE001 - best-effort repair, validated after
            pass
    return cfg


def split_simulator(client, story, criteria_summary, checks, spec_notes="",
                    log_fn=print, max_redrafts=1):
    """Block-by-block stage 3. Returns a validated simulator config."""
    from syngen.menu import required_blocks
    blocks = sorted(required_blocks(checks))
    log_fn(f"Stage 3 split: drafting core + {len(blocks)} optional block(s): "
           f"{blocks or ['none']}")
    base = {"seed": DEFAULT_SEED, "time_model": dict(DEFAULT_TIME_MODEL),
            "output": dict(DEFAULT_OUTPUT)}
    corrective = ""
    last_err = None
    for attempt in range(max_redrafts + 1):
        core = draft_core(client, story, criteria_summary, checks, spec_notes,
                          log_fn, corrective=corrective)
        candidate = {**base, **core}
        for block in OPTIONAL_BLOCKS:
            if block not in blocks:
                continue
            part = draft_block(client, block, story, criteria_summary, checks,
                               spec_notes, log_fn)
            if part:
                candidate[block] = part
            else:
                log_fn(f"Stage 3 split: block '{block}' came back empty.")
        _normalize(candidate)
        try:
            validated = validate_simulator_doc(candidate)
        except ConfigError as e:
            last_err = e
            if attempt >= max_redrafts:
                raise
            corrective = str(e)
            log_fn(f"Stage 3 split: assembly invalid ({e}) - re-drafting core.")
            continue
        n_q = len(validated["time_model"]["quarter_labels"])
        log_fn(f"Stage 3 split assembled: {validated['accounts']['count']} "
               f"accounts, {validated['opportunities']['per_quarter']}/qtr x "
               f"{n_q} quarters, blocks={[b for b in OPTIONAL_BLOCKS if b in validated]}")
        return validated
    raise ConfigError(f"stage-3 split failed after {max_redrafts + 1} "
                      f"attempts: {last_err}")
