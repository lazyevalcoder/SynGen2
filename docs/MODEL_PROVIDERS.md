# Model Providers: thinking control and usage capture (P15)

> Status: implemented on `refactor/stage23-phases` (2026-09-12). 498 tests
> green. Local llama.cpp remains the default; hosted providers are opt-in.

## DeepSeek / OpenAI-compatible thinking control

Probed the hosted API directly (2026-09-12):

| Parameter | Effect |
|---|---|
| `reasoning: {effort: none/low/medium/high}` | **ignored** (reasoning tokens unchanged) |
| `reasoning_effort` | **ignored** |
| `thinking: {type: disabled}` | **works** - reasoning_tokens become null |
| `thinking: {type: enabled, budget_tokens: N}` | no clear cap observed |

So there is no reliable "medium"; the lever is on/off via `thinking.type`.

The client now supports provider fragments:

```json
{
  "backend": "openai",
  "api_base": "https://api.deepseek.com/v1",
  "model": "deepseek-flash",
  "thinking_disable_body": {"thinking": {"type": "disabled"}},
  "thinking_enable_body":  {"thinking": {"type": "enabled", "budget_tokens": 1024}}
}
```

- `thinking_disable_body` is merged when a task profile sets
  `enable_thinking=False` (precheck, critic, coverage_audit, claim_forms,
  simulator_block, story_diff, rework_judge, fixer).
- `thinking_enable_body` is merged otherwise.
- llama.cpp keeps `chat_template_kwargs`; OpenRouter keeps `reasoning.effort`
  (both unchanged; the fragments default to `{}`).

**Known limit:** `reasoning_budget_tokens` is a llama.cpp-only field, so on a
hosted backend the *drafting* tasks (decompose, criterion_params,
simulator_core, knob_proposal) still think unbounded. Completion tokens
dominated the first measured DeepSeek flight (below), so a drafting budget is
the next lever.

## Usage capture

`syngen/usage.py::write_usage` writes `<session>/usage.json`
(`calls`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `elapsed_s`,
`prompt_chars`, `completion_chars`) and the runner/`new` path prints it. The
runner also catches a stage crash, escalates it, and still writes usage.

## First measured DeepSeek flight

`scenario_14`, `--all-stages --stage23 split`, thinking disabled for
mechanical tasks:

- **LANDED** 3/3 criteria on iteration 1 (forecast 109% ±2, plan 100% ±2,
  slippage +14.3pp vs ≥10pp).
- **52 calls, 241,289 tokens** (prompt 92,969 / completion 148,320), 708s.
- Completion > prompt: reasoning still dominates; the mechanical disable
  helped but drafting still thinks freely.

Also fixed en route: a pre-flight corrective re-draft that raised
`ConfigError` used to crash the CLI (scenario 14 exposed it); it now
escalates.
