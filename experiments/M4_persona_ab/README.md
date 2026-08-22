# M4 Persona Critique A/B (GAPS G1 verdict)

**Date:** 2026-08-22 · **Runner:** `run_ab.py` (results in `results.jsonl`)

## Design
Three stories spanning all landed domains (discount erosion, quota attainment, cycle slowdown). Each ran the full pipeline twice with the live llama.cpp/Ornith-35B stack, batch mode, iteration cap 6:
- **personas arm** — persona critique feeds spec notes into simulator drafting (as shipped since M2)
- **control arm** — personas skipped entirely; simulator drafted from criteria alone

## Results

| Story | Arm | Status | Iterations | Proposals | Elapsed | Lint (block/advise) |
|---|---|---|---|---|---|---|
| discount | personas | converged | 2 | 1 | 177s | 0/1 |
| discount | control | converged | 2 | 1 | 169s | 0/1 |
| quota | personas | converged | 1 | 0 | 176s | 0/1 |
| quota | control | converged | 1 | 0 | **135s** | 0/1 |
| slowdown | personas | converged | 2 | 1 | 163s | 0/1 |
| slowdown | control | converged | **1** | **0** | **142s** | 0/1 |

## Verdict: NO measurable benefit — demoted to opt-in

- Convergence quality identical everywhere; control was equal-or-better on iterations (2 of 3 stories) and consistently ~35s faster (the persona call's own latency)
- Draft quality (lint findings) identical across arms

**Disposition:** `use_personas` now defaults OFF; `--personas` CLI flag re-enables. Revisit if criteria/spec quality degrades on unfamiliar domains (M4+ second-domain work is the natural re-test ground) — track any lint escapes or convergence regressions here.

Caveat: n=3 stories, one seed each. This verdict justifies demotion from the default path, not deletion — the code path stays one flag away.
