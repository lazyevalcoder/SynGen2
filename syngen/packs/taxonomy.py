"""ClaimTaxonomy implementation over a loaded DomainPack (M6 P1).

The guard and later multi-agent roles consume the pack through this
adapter rather than touching raw JSON: cells(), cohorts(), and
cells_for_check() are the stable read surface.
"""
from .api import ClaimTaxonomy
from . import cohorts as cohort_algebra


class PackTaxonomy(ClaimTaxonomy):
    def __init__(self, pack):
        cells = (pack.claims_matrix or {}).get("cells", [])
        self._cells = {c["id"]: c for c in cells}
        self._by_check = {}
        for cell in cells:
            for check in cell.get("checks", []):
                self._by_check.setdefault(check, []).append(cell)
        self._signatures = (pack.check_signatures or {}).get(
            "signatures", {})

    def cells(self):
        return dict(self._cells)

    def cells_for_check(self, check_id):
        return list(self._by_check.get(check_id, []))

    def cohorts(self):
        return {name: (lambda df, _n=name: cohort_algebra.mask(df, _n))
                for name in cohort_algebra.names()}

    def check_catalog(self):
        """Generated 'name: params - usage' lines, in matrix order."""
        seen, lines = set(), []
        for cell in self._cells.values():
            for check in cell.get("checks", []):
                if check in seen:
                    continue
                seen.add(check)
                vocab = cell.get("vocab")
                lines.append(f"- {check}: {vocab}" if vocab
                             else f"- {check}")
        return "\n".join(lines)

    def check_names(self, sep=" | "):
        """All registered check names, in matrix order."""
        seen = []
        for cell in self._cells.values():
            for check in cell.get("checks", []):
                if check not in seen:
                    seen.append(check)
        return sep.join(seen)

    def check_knowledge(self):
        """Generated parameter-semantics notes for the knob proposer
        (P5 WP7): sign conventions and pinned-quantity facts per check,
        straight from the signature registry."""
        lines = []
        for check, sig in self._signatures.items():
            for key in ("directional_params", "pinned_quantity"):
                note = sig.get(key)
                if isinstance(note, dict):
                    for pname, desc in note.items():
                        lines.append(f"- {check}.{pname}: {desc}")
                elif isinstance(note, str):
                    lines.append(f"- {check}: {note}")
            for coord in sig.get("coordinates", []):
                note = coord.get("notes")
                if note and coord.get("space"):
                    lines.append(f"- {check}.{coord.get('param')}: {note}")
        return "\n".join(lines)

    def authoring_guide(self):
        """Drafter constraints (P9.1 "skills").

        Curated doctrine (`packs/revops/prompts/authoring_guide.txt`) plus
        generated facts rendered from the signature registry, so the rules
        cannot drift from what the engine can actually build. Injected into
        the criteria-drafting prompt and the rework judge.
        """
        from syngen.prompts import load_prompt
        curated = load_prompt("authoring_guide").strip()
        facts = self._generated_authoring_facts()
        return curated + ("\n\n" + facts if facts else "")

    def _generated_authoring_facts(self):
        lines = ["GENERATED PARAMETER FACTS (from the check registry):"]
        scope = []
        for check, sig in self._signatures.items():
            for coord in sig.get("coordinates", []):
                space = coord.get("space")
                if not space:
                    continue
                allowed = " (or '_all_')" if coord.get("allow_all") else ""
                scope.append(f"- {check}.{coord.get('param')}: one of the "
                             f"config's {space}{allowed}")
        if scope:
            lines.append("Scoping - only address units that exist:")
            lines.extend(scope)
        sem = []
        for check, sig in self._signatures.items():
            for key in ("directional_params", "pinned_quantity"):
                note = sig.get(key)
                if isinstance(note, dict):
                    for pname, desc in note.items():
                        sem.append(f"- {check}.{pname}: {desc}")
                elif isinstance(note, str):
                    sem.append(f"- {check}: {note}")
        if sem:
            lines.append("Direction and pinned quantities:")
            lines.extend(sem)
        return "\n".join(lines)
