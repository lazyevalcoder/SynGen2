# Prompts Log — SynGen Experiments

Prompts used against the local llama.cpp endpoint (`http://127.0.0.1:8080`, OpenAI-compatible `/v1/chat/completions`). Kept for future reference when building the harness's prompt library.

---

## Prompt 1 — Experiment A: Story → Metrics Decomposition

**Purpose:** Test whether an LLM can decompose a business story into quantified, script-checkable acceptance criteria. This validates the core premise of SynGen Phase 1.

**System prompt:**
```
You are a senior Revenue Operations analyst. You will be given a business
narrative. Your job is to reverse-engineer it into measurable acceptance
criteria that a generated dataset must satisfy for the story to be true.

Rules:
- Every criterion MUST be computable from tabular data (accounts and
  opportunities tables). No subjective criteria.
- Give each criterion a target value and a tolerance.
- State explicitly which table columns/fields would be needed to compute it.
- Flag any claim in the story that is ambiguous or under-specified, and
  state the assumption you chose to resolve it.
```

**User prompt:**
```
Story:
"Win rates held steady this year, but average deal discounts crept up from
12% to 18%, quietly eroding margins. The bleed is worst in EMEA, where reps
are discounting aggressively to close end-of-quarter deals."

Context you may assume (not stated in the story):
- Fiscal year FY26, quarters Q1-Q4
- Regions: AMER, EMEA, APAC
- Data model: accounts table + opportunities table (list price, realized
  price, discount %, close date, stage, region)

Produce:
1. A numbered list of acceptance criteria with target + tolerance.
2. Required fields per criterion.
3. Ambiguities found in the story and your resolution of each.
```

**Result:** SUCCESS. Model: Ornith-1.5-35B-Q4_K_M (reasoning model — emits `reasoning_content` before `content`; needs `max_tokens` ≥ 8192 so reasoning doesn't exhaust the budget). Full output in `A_story_to_metrics/llm_decomposition.md`.

Key findings:
- LLM produced 5 criteria mapping ~1:1 to the human draft's AC1–AC7.
- Identical on: win-rate steadiness definition, monotonic discount trend.
- Differed only on tolerance magnitudes (±1.5pp vs ±2pp) and window definitions (30d vs 14d end-of-quarter) — resolved in `acceptance_criteria.md`.
- Valuable catch: flagged that true margin erosion is NOT computable without cost data; our AC7 uses realized/list price ratio as a computable proxy instead.
- Suggested adding an `owner` (rep) column for realism → adopted for Experiment B.

**Lesson for harness:** reasoning models need large token budgets and both response fields captured; ambiguity resolution (windows, tolerances) should be an explicit spec-clarification step, not left implicit.

---

## Notes for future harness prompts (placeholder)
- Phase 2 persona critique prompts (domain expert / BI engineer / outsider) — TBD
- Simulator knob adjustment prompts — TBD
