### Narrative

>NA missed plan and revenue declining driven by miss in Enterprise segment. Pipeline coverage is strong at 3.2x but conversion is below lq and rolling 4q. There is a trend in sales activity declining due to rep attrition (2) in Enterprise.

### Architecture:

```
                         USER
                           │
                           │ natural language
                           ▼
                 ┌───────────────────┐
                 │ Scenario Interpreter│
                 └─────────┬─────────┘
                           │
                           ▼
                 ┌───────────────────┐
                 │ Scenario Model    │
                 │                   │
                 │ entities          │
                 │ metrics           │
                 │ dimensions        │
                 │ events            │
                 │ relationships     │
                 │ assumptions       │
                 │ constraints       │
                 │ causal links      │
                 └─────────┬─────────┘
                           │
                           ▼
                 ┌───────────────────┐
                 │ Schema Planner    │
                 └─────────┬─────────┘
                           │
                           ▼
                 ┌───────────────────┐
                 │ Data Generator    │
                 └─────────┬─────────┘
                           │
                           ▼
                 ┌───────────────────┐
                 │ Scenario Validator│
                 └─────────┬─────────┘
                           │
                    ┌──────┴──────┐
                    │             │
                  PASS           FAIL
                    │             │
                    ▼             │
                 Dataset     ← regenerate
```