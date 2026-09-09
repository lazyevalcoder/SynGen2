"""Deterministic schema linter for SynGen data specs (Experiment E).

Rules:
  R1 duplicate_grain      - two entities claiming the same grain
  R2 stored_aggregate     - entity that looks like a pre-computed rollup
  R3 dangling_reference   - FK-style fields (_id suffix) without declared reference
  R4 taxonomy_completeness- dimension uses a subset of the known real-world
                            taxonomy without an explicit exclusion note (ADVISORY)
  R5 redundant_status     - multiple fields encoding the same outcome semantics
"""
import json
import re
import sys
from pathlib import Path

KNOWN_TAXONOMIES = {
    "segment": {"Enterprise", "Mid-Market", "SMB", "CSB", "Consumer", "Small Business"},
}

CANONICAL_SETS = {
    frozenset({"AMER", "EMEA", "APAC"}),
    frozenset({"Enterprise", "Mid-Market", "SMB", "CSB"}),
}

AGGREGATE_NAME_PATTERNS = re.compile(
    r"(summary|metrics|totals|rollup|agg|kpi|by_(quarter|month|region|segment))", re.I
)
AGGREGATE_GRAIN_PATTERNS = re.compile(
    r"one row per (quarter|month|year|region|segment|day)\b.*per\b|\bby (quarter|region|segment)", re.I
)
STATUS_SEMANTICS = re.compile(r"(stage|status|win_loss|outcome|close)", re.I)


def lint(spec):
    findings = []
    entities = spec.get("entities", [])
    names = {e["name"].lower() for e in entities}

    # R1 duplicate grain
    seen_grains = {}
    for e in entities:
        g = re.sub(r"\s+", " ", e.get("grain", "").lower().replace("/", " ").replace("opportunity deal", "deal"))
        g = g.replace("one row per ", "").strip()
        if g in seen_grains:
            findings.append(("R1", "FAIL",
                             f"'{e['name']}' duplicates grain of '{seen_grains[g]}' ('{g}')"))
        else:
            seen_grains[g] = e["name"]

    # R2 stored aggregate
    for e in entities:
        name_hit = AGGREGATE_NAME_PATTERNS.search(e["name"])
        grain_hit = AGGREGATE_GRAIN_PATTERNS.search(e.get("grain", ""))
        has_id_field = any(f["name"].lower().endswith("_id") and
                           f["name"].lower() == e["name"].lower() + "_id"
                           for f in e.get("fields", []))
        if (name_hit or grain_hit) and not has_id_field:
            kind = "name" if name_hit else "grain"
            findings.append(("R2", "FAIL",
                             f"'{e['name']}' looks like a stored aggregate ({kind} pattern); "
                             "compute as derived view instead"))

    # R3 dangling references
    for e in entities:
        declared = set()
        refs = e.get("references")
        if isinstance(refs, str) and refs.lower() not in ("null", "none", ""):
            declared = {r.strip().lower() for r in refs.split(",")}
        elif isinstance(refs, list):
            declared = {r.lower() for r in refs}
        ename = e["name"].lower()
        pk_forms = {ename + "_id", ename.rstrip("s") + "_id"}
        for f in e.get("fields", []):
            fname = f["name"].lower()
            if fname.endswith("_id") and fname not in pk_forms:
                stem = fname[:-3]
                candidates = {stem, stem + "s"}
                if candidates & declared:
                    continue
                if any(c in n or c == n.rstrip("s") for n in names for c in candidates):
                    findings.append(("R3", "WARN",
                                     f"'{e['name']}.{fname}' looks like a FK but "
                                     f"'references' is '{refs}'"))

    # R4 taxonomy completeness (advisory)
    for e in entities:
        for f in e.get("fields", []):
            vals = f.get("values")
            if not isinstance(vals, list):
                continue
            vset = {str(v) for v in vals}
            if frozenset(vset) in CANONICAL_SETS:
                continue
            for tax_name, tax_values in KNOWN_TAXONOMIES.items():
                overlap = vset & tax_values
                if overlap and len(overlap) >= 2 and vset < tax_values:
                    missing = sorted(tax_values - vset)
                    findings.append(("R4", "ADVISE",
                                     f"'{e['name']}.{f['name']}' uses {sorted(vset)}; "
                                     f"real-world taxonomy likely includes {missing}. "
                                     "Include full taxonomy unless story excludes it"))

    # R5 redundant status fields
    for e in entities:
        status_fields = [f["name"] for f in e.get("fields", [])
                         if f.get("type") != "date" and STATUS_SEMANTICS.search(f["name"])]
        value_sets = [set(str(v).lower() for v in f.get("values", []))
                      for f in e.get("fields", [])
                      if f.get("type") != "date" and f["name"] in status_fields
                      and STATUS_SEMANTICS.search(f["name"])]
        overlapping = False
        for i in range(len(value_sets)):
            for j in range(i + 1, len(value_sets)):
                a_values, b_values = value_sets[i], value_sets[j]
                a_tokens = set().union(*(v.split() for v in a_values))
                b_tokens = set().union(*(v.split() for v in b_values))
                if a_values & b_values or a_tokens & b_tokens:
                    overlapping = True
        if len(status_fields) > 1 and overlapping:
            findings.append(("R5", "FAIL",
                             f"'{e['name']}' has overlapping status fields "
                             f"{status_fields}; keep one canonical lifecycle field"))

    return findings


def main():
    spec_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "llm_specs")
    total_fail = 0
    for path in sorted(spec_dir.glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        findings = lint(spec)
        print(f"\n=== {path.name}: {len(findings)} finding(s) ===")
        if not findings:
            print("  clean")
        for rule, severity, msg in findings:
            print(f"  [{rule}/{severity}] {msg}")
            if severity != "ADVISE":
                total_fail += 1
    print(f"\nTotal non-advisory findings across all specs: {total_fail}")


if __name__ == "__main__":
    main()
