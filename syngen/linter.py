"""Deterministic schema linter for SynGen simulator configs (FR4).

Ported from experiments/E/schema_linter.py and adapted: E linted free-form
LLM spec JSON; this lints the actual simulator.json shape. Rule IDs are kept
for continuity with the experiment log.

Rules:
  R1 duplicate_grain      - extra top-level block that duplicates a known
                            entity/fact table under a synonym name
  R2 stored_aggregate     - block that looks like a pre-computed rollup
  R3 dangling_reference   - field-style spec ending in _id with no declared
                            reference target
  R4 taxonomy_completeness- dimension uses a subset of the known real-world
                            taxonomy without an explicit exclusion (ADVISORY)
  R5 redundant_status     - multiple sibling fields encoding the same outcome
                            semantics

Also provides structure_findings(): post-generation check that the workbook's
sheets/columns match what the fixed engine is supposed to produce (generalizes
Experiment F's structure_check.py).
"""
import re

KNOWN_BLOCKS = {"seed", "time_model", "output", "accounts", "opportunities"}

FACT_SYNONYMS = re.compile(
    r"(deals?|pipeline|opps?|transactions?|records?|activities?)$", re.I)
ENTITY_SYNONYMS = re.compile(
    r"(customers?|companies?|clients?|prospects?)$", re.I)
AGGREGATE_NAME_PATTERNS = re.compile(
    r"(summary|metrics|totals|rollup|agg|kpi|by_(quarter|month|region|segment))",
    re.I)
STATUS_SEMANTICS = re.compile(r"(stage|status|win_loss|outcome|close)", re.I)

KNOWN_TAXONOMIES = {
    "segments": {"Enterprise", "Mid-Market", "SMB", "CSB", "Consumer",
                 "Small Business"},
}
CANONICAL_SETS = {
    frozenset({"AMER", "EMEA", "APAC"}),
    frozenset({"Enterprise", "Mid-Market", "SMB", "CSB"}),
}


def _block_entities(cfg):
    """Top-level keys beyond the known engine blocks."""
    return [k for k in cfg if k not in KNOWN_BLOCKS and not k.startswith("_")]


def lint(cfg):
    findings = []

    # R1 duplicate grain / synonym tables (F6 leak path: engine would
    # silently IGNORE an extra 'deals' block - catch it at Gate 1 instead)
    for block in _block_entities(cfg):
        if FACT_SYNONYMS.search(block) or ENTITY_SYNONYMS.search(block):
            findings.append(("R1", "FAIL",
                             f"'{block}' duplicates a known table under a "
                             "synonym name; keep one canonical fact/entity "
                             "table"))
        else:
            findings.append(("R1", "WARN",
                             f"unknown top-level block '{block}' - the "
                             "generator will silently ignore it"))

    # R2 stored aggregate
    for block in _block_entities(cfg):
        if AGGREGATE_NAME_PATTERNS.search(block):
            findings.append(("R2", "FAIL",
                             f"'{block}' looks like a stored aggregate; "
                             "compute as derived view instead"))

    # R3 dangling references: any nested 'fields' spec with *_id entries
    # whose reference target is not declared anywhere in the config
    declared = set(_block_entities(cfg)) | {"accounts", "opportunities"}
    for block_name, block in cfg.items():
        if not isinstance(block, dict):
            continue
        fields = block.get("fields")
        if not isinstance(fields, dict):
            continue
        refs = block.get("references")
        declared_refs = set()
        if isinstance(refs, str):
            declared_refs = {r.strip().lower() for r in refs.split(",")}
        elif isinstance(refs, list):
            declared_refs = {str(r).lower() for r in refs}
        for fname, fspec in fields.items():
            lname = str(fname).lower()
            if not lname.endswith("_id"):
                continue
            stem = lname[:-3]
            # NOTE: the owning block's own name deliberately excluded -
            # '<other>_id' inside a block must point at a DECLARED target
            candidates = {stem, stem + "s"}
            if candidates & declared_refs:
                continue
            if not any(c in declared or c.rstrip("s") in declared
                       or c + "s" in declared for c in candidates):
                findings.append(("R3", "WARN",
                                 f"'{block_name}.{fname}' looks like a FK but "
                                 f"'{stem}' is not a declared entity"))

    # R4 taxonomy completeness (advisory): categorical distributions in
    # accounts against known real-world taxonomies
    accounts = cfg.get("accounts", {})
    if isinstance(accounts, dict):
        for dim, tax_values in KNOWN_TAXONOMIES.items():
            spec = accounts.get(dim)
            if not isinstance(spec, dict):
                continue
            vset = {str(v) for v in spec}
            if frozenset(vset) in CANONICAL_SETS:
                continue
            overlap = vset & tax_values
            if overlap and len(overlap) >= 2 and vset < tax_values:
                missing = sorted(tax_values - vset)
                findings.append(("R4", "ADVISE",
                                 f"accounts.{dim} uses {sorted(vset)}; "
                                 f"real-world taxonomy likely includes "
                                 f"{missing}. Include the full taxonomy "
                                 "unless the story excludes it"))

    # R5 redundant status fields inside any block's 'fields' spec
    for block_name, block in cfg.items():
        if not isinstance(block, dict):
            continue
        fields = block.get("fields")
        if not isinstance(fields, dict):
            continue
        status_fields = [f for f in fields if STATUS_SEMANTICS.search(str(f))]
        value_sets = []
        for f in status_fields:
            fspec = fields[f]
            values = fspec.get("values", []) if isinstance(fspec, dict) else []
            value_sets.append({str(v).lower() for v in values})
        overlapping = False
        for i in range(len(value_sets)):
            for j in range(i + 1, len(value_sets)):
                a, b = value_sets[i], value_sets[j]
                a_tokens = set().union(*(v.split() for v in a))
                b_tokens = set().union(*(v.split() for v in b))
                if (a & b) or (a_tokens & b_tokens):
                    overlapping = True
        if len(status_fields) > 1 and overlapping:
            findings.append(("R5", "FAIL",
                             f"'{block_name}' has overlapping status fields "
                             f"{status_fields}; keep one canonical lifecycle "
                             "field"))

    return findings


def has_blocking(findings):
    """True if any finding should block acceptance: FAIL severity.
    WARN surfaces loudly but does not dead-end the user; ADVISE is
    informational (E's F8 human-decision pattern)."""
    return any(severity == "FAIL" for _, severity, _ in findings)


# --- post-generation structural check ---------------------------------------

EXPECTED_SHEETS = {
    "accounts": [
        "account_id", "account_name", "region", "segment", "industry",
        "market_potential_usd"],
    "opportunities": [
        "opportunity_id", "account_id", "owner", "region", "segment",
        "fiscal_quarter", "created_date", "close_date", "stage",
        "list_price", "discount_pct", "realized_price"],
    "quarterly_summary": None,  # derived view; presence checked, columns free
    "quota_plan": ["segment", "fiscal_quarter", "target_realized_usd"],
    "_synngen_meta": None,
}
OPTIONAL_SHEETS = {"quota_plan"}  # present only when the config has quotas


def structure_findings(xl_file):
    """Workbook must match the engine's sheet/column contract exactly.

    Extra or missing sheets mean someone hand-edited output or the generator
    drifted from its contract - both are gate-blocking. Optional sheets are
    column-checked only when present.
    """
    import pandas as pd

    findings = []
    xl = pd.ExcelFile(xl_file)
    present = set(xl.sheet_names)
    for sheet, columns in EXPECTED_SHEETS.items():
        if sheet not in present:
            if sheet in OPTIONAL_SHEETS:
                continue
            findings.append(("S1", "FAIL", f"missing required sheet '{sheet}'"))
            continue
        if columns is not None:
            actual = list(pd.read_excel(xl_file, sheet_name=sheet).columns)
            if actual != columns:
                missing = [c for c in columns if c not in actual]
                extra = [c for c in actual if c not in columns]
                findings.append(("S1", "FAIL",
                                 f"sheet '{sheet}' column mismatch; "
                                 f"missing={missing} unexpected={extra}"))
    for sheet in sorted(present - set(EXPECTED_SHEETS)):
        findings.append(("S1", "FAIL",
                         f"unexpected sheet '{sheet}' in workbook"))
    return findings
