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

    def cells(self):
        return dict(self._cells)

    def cells_for_check(self, check_id):
        return list(self._by_check.get(check_id, []))

    def cohorts(self):
        return {name: (lambda df, _n=name: cohort_algebra.mask(df, _n))
                for name in cohort_algebra.names()}
