# Experiment D — Manual Convergence Loop

## What this is
The core simulation loop, done by hand: tweak knobs in `simulator.json` → regenerate → validate → repeat, until ALL acceptance criteria pass within tolerance.

## Why it matters
This answers the single biggest risk question: **is convergence achievable at all?** If a human can't steer simulator.json knobs to land the story, automating the loop won't help — the concept needs rethinking. If a human can, automating it later (agent or optimizer) is straightforward engineering.

## Method
1. Start from Experiment B's baseline config.
2. Run validator → identify failing criteria.
3. Adjust the relevant knob(s) in `simulator.json`.
4. Regenerate + revalidate. Record each iteration in `iterations_log.md`.
5. Repeat 5–10 rounds max.

## What we're learning (beyond pass/fail)
- How many knobs are needed?
- Which knobs are sensitive / which are dead?
- Do knobs interact badly (fixing one breaks another)?
- Roughly how many iterations to converge? (informs automation design)

## Pass condition
All acceptance criteria green within tolerances within ~10 manual iterations.

## Gate
On success: the concept is proven end-to-end manually. Only then do we build the agentic harness.
