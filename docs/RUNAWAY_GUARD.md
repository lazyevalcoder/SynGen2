# Runaway Guard: hard per-flight LLM budgets (P18)

> Status: implemented on `refactor/stage23-phases` (2026-09-12). 520 tests
> green.

## Why
With a hosted API, an unbounded run burns money. There was **no global cap** -
only per-loop limits (coverage re-drafts, calibrate re-drafts, rework rounds,
iteration/proposal caps). A failure could stack: stage-2 re-drafts (coverage +
critic + critic re-check + consistency + menu gate) x a stage retry, each a
full high-effort prompt. Scenario 15 cost **52 calls / 334,739 tokens / 983s
and still failed**.

## The guard
`LLMClient` now enforces a hard per-flight budget, checked **before every
call**:

| Cap | Meaning |
|---|---|
| `max_calls` | total LLM calls |
| `max_total_tokens` | total prompt+completion tokens |
| `max_seconds` | wall clock since the client was created |
| `max_usd` | estimated spend (needs `price_per_mtok_in/out`) |

On exceed it raises `BudgetExceeded`. The runner (and the classic
`run_new_story`) catch it and return an honest **`budget_exceeded`**
escalation - never a crash, and never a retry/rewind past the stop.

## Defaults
- **Local llama.cpp: unlimited** (no change).
- **Hosted backends: `40 calls / 150k tokens / 600s`** applied automatically
  unless the config or CLI overrides them. `allow_unbounded: true` (or
  `--allow-unbounded`) disables the defaults explicitly.

## CLI
```
python -m syngen new --story-file ... --llm-config llm_configs/deepseek.json \
    --max-calls 30 --max-tokens 120000 --max-seconds 420 --max-usd 0.50
```
Available on `new`, `run`, and `fly`.

## Stage-2 re-draft budget
`stage_criteria` counts **all** re-drafts (coverage + critic + consistency +
menu) against one budget (4). When spent it escalates `criteria_budget` instead
of stacking guards. Stage retries/rewinds consume the same global budget.

## Visibility
`<session>/usage.json` now includes a `budget` block (caps, used, estimated
USD), and the run prints `LLM usage: ...` + `Budget: n/N calls, ...`.

## Note on retry multipliers
`chat_json` retries parse up to 3x and HTTP retries up to `max_http_retries`;
the budget cap bounds the *total* regardless, so a single bad task can no
longer multiply unbounded.

## Tests
`tests/test_p18_budget.py` (hosted defaults, allow-unbounded, calls/tokens/usd
caps, chat checks before spending) + a runner test that a 1-call budget
escalates `budget_exceeded`.
