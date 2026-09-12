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


def _render(name, story, criteria_summary, checks, spec_notes,
            core_units="(not drafted yet)"):
    from syngen.menu import required_blocks, required_features
    return load_prompt(
        f"blocks/{name}",
        story=story[:2000],
        criteria=criteria_summary,
        spec=(spec_notes or "none")[-1500:],
        check_facts=_facts(checks),
        required_blocks=", ".join(sorted(required_blocks(checks))) or "none",
        required_features=", ".join(sorted(required_features(checks))) or "none",
        core_units=core_units,
    )


def _core_units(core):
    """The unit names the core (accounts) actually chose, so block prompts
    (quota/capacity) reference real names instead of inventing them. Fixes the
    cross-block territory mismatch that killed scenario 15 (both models)."""
    acc = (core or {}).get("accounts") or {}
    parts = []
    for dim in ("territories", "regions", "segments"):
        val = acc.get(dim)
        if isinstance(val, dict) and val:
            parts.append(f"- accounts.{dim}: {sorted(val)}")
    return "\n".join(parts) or "(none drafted)"


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
                spec_notes="", log_fn=print, corrective="",
                core_units="(not drafted yet)"):
    """Draft one optional block; None means the block was omitted/failed."""
    system = _render(block, story, criteria_summary, checks, spec_notes,
                     core_units=core_units)
    if corrective:
        system += ("\n\nCORRECTIVE FINDINGS - your previous block was missing "
                   "or unusable; fix ALL of these:\n" + corrective)
    result = chat_json(client, f"simulator_{block}", system,
                       "Produce the block JSON now.")
    part = result.get(block) if isinstance(result, dict) else None
    return part if isinstance(part, dict) else None


def _repair_missing(client, story, criteria_summary, checks, spec_notes,
                    candidate, missing, log_fn, core_units="(not drafted yet)"):
    """Targeted re-draft of whatever the buildability gate found missing."""
    from syngen.phases.buildability import missing_blocks
    names = missing_blocks(missing)
    core_missing = any(b in ("accounts", "opportunities") for b in names)
    if core_missing:
        core = draft_core(client, story, criteria_summary, checks, spec_notes,
                          log_fn, corrective="; ".join(missing))
        candidate.update(core)
        core_units = _core_units(candidate)
    for block in names:
        if block in OPTIONAL_BLOCKS:
            part = draft_block(client, block, story, criteria_summary, checks,
                               spec_notes, log_fn, corrective="; ".join(missing),
                               core_units=core_units)
            if part:
                candidate[block] = part
    return candidate


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
    """Block-by-block stage 3. Returns a validated simulator config.

    Before the stage may complete, a deterministic buildability gate (P13)
    checks that every criterion's required blocks/features are present; a
    missing piece is re-drafted (bounded) or the stage fails honestly."""
    from syngen.menu import required_blocks
    from syngen.phases.buildability import (BuildabilityError,
                                            cross_block_findings,
                                            verify_config)
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
        core_units = _core_units(core)
        candidate = {**base, **core}
        for block in OPTIONAL_BLOCKS:
            if block not in blocks:
                continue
            part = draft_block(client, block, story, criteria_summary, checks,
                               spec_notes, log_fn, core_units=core_units)
            if part:
                candidate[block] = part
            else:
                log_fn(f"Stage 3 split: block '{block}' came back empty.")
        _normalize(candidate)

        missing = verify_config(candidate, checks) + cross_block_findings(candidate)
        if missing:
            log_fn(f"Stage 3 buildability: {len(missing)} missing/mismatched "
                   "item(s) - targeted re-draft.")
            _repair_missing(client, story, criteria_summary, checks, spec_notes,
                            candidate, missing, log_fn, core_units=core_units)
            _normalize(candidate)
            missing = (verify_config(candidate, checks)
                       + cross_block_findings(candidate))
        if missing:
            raise BuildabilityError(
                "stage-3 buildability failed: " + "; ".join(missing))

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
               f"{n_q} quarters, blocks="
               f"{[b for b in OPTIONAL_BLOCKS if b in validated]}")
        return validated
    raise ConfigError(f"stage-3 split failed after {max_redrafts + 1} "
                      f"attempts: {last_err}")
