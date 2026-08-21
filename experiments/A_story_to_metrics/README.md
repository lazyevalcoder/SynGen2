# Experiment A — Story → Quantified Acceptance Criteria

## What this is
The first gate of SynGen. We take a natural-language business story and convert it into a list of **quantified acceptance criteria with tolerances** — numbers a script can check without human judgment.

## Why it matters
Everything downstream (generation, simulation, validation) needs an objective function. If a story cannot be decomposed into measurable targets, the whole concept fails here — cheaply.

## The story (medium complexity, RevOps)
> **Win rates held steady this year, but average deal discounts crept up from 12% to 18%, quietly eroding margins. The bleed is worst in EMEA, where reps are discounting aggressively to close end-of-quarter deals.**

## Method
1. Draft acceptance criteria derived from every claim in the story (human/LLM-assisted).
2. Assign each a target value and tolerance.
3. Cross-check: ask the local llama.cpp LLM to independently decompose the same story; compare its criteria against ours. Divergences reveal ambiguity in the decomposition task itself.
4. Review: does each criterion map to something computable from a tabular dataset?

## Pass condition
A metrics list where every item is computable from generated data (opportunities/accounts tables) and jointly captures "the story landed."

## Deliverable
`acceptance_criteria.md` — the signed-off criteria list used by Experiments C and D.
