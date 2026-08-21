# From Business Narrative to Scenario-Driven Synthetic Data

When we ask an LLM to generate a sales pipeline dataset, we often start with a request like:

> “Generate a sales pipeline dataset.”

The model will typically respond by creating tables such as leads, opportunities, deals, sales activities, sales representatives, and products, along with distributions for each field.

That is useful if the goal is simply to create a plausible-looking CRM dataset.

But it breaks down when the actual goal is **scenario modelling**.

A business user rarely thinks in terms of database tables. They think in terms of a business situation:

> “NA missed plan and revenue is declining, driven by a miss in Enterprise. Pipeline coverage is strong at 3.2x, but conversion is below last quarter and rolling 4Q. Sales activity is also declining because of rep attrition — two Enterprise reps left.”

This is not a schema specification. It is a **business story**.

The challenge is that this story contains much more information than the obvious nouns in the sentence. It contains outcomes, trends, causal relationships, time relationships, metrics, benchmarks, and implied constraints. If the LLM jumps directly from this narrative to a database schema, much of that meaning gets lost.

The solution is to introduce an intermediate layer between the user's narrative and the data model.

I think of this as a **Scenario Specification** or **Business Scenario Model**.

---

## The Missing Layer

In software development, a PRD acts as a guiding artifact between an idea and implementation. A similar concept is needed for scenario-driven synthetic data.

The overall flow should be:

```text
User Narrative
      ↓
Scenario Understanding
      ↓
Scenario Specification
      ↓
Domain / Entity Model
      ↓
Data Generation Plan
      ↓
Synthetic Dataset
      ↓
Scenario Validation
```

The critical idea is that the LLM should **not immediately start designing tables**.

First, it needs to understand:

> What world is the user asking me to simulate?

Only after that should it determine what data is required to represent that world.

This changes the problem from:

> “Generate some realistic sales data.”

to:

> “Construct a synthetic sales organization whose data exhibits these specific business behaviors.”

That is a much more powerful problem.

---

# The Business Narrative Contains a Hidden Model

Consider the original scenario:

> “NA missed plan and revenue declining driven by miss in Enterprise segment. Pipeline coverage is strong at 3.2x but conversion is below LQ and rolling 4q. There is a trend in sales activity declining due to rep attrition (2) in Enterprise.”

A naive system might extract:

* North America
* Enterprise
* revenue
* pipeline
* conversion
* sales activity
* reps
* attrition

and create tables around them.

But the real scenario contains much more.

It says that:

**North America missed plan.**

Therefore:

```text
NA actual revenue < NA revenue plan
```

It says that:

**Revenue is declining.**

Therefore:

```text
Current revenue < previous-period revenue
```

or, more realistically, there is a statistically meaningful downward trend.

It says:

**Enterprise is driving the miss.**

That does not merely mean Enterprise revenue is low.

It means Enterprise should account for a disproportionate share of the North American revenue shortfall.

For example:

```text
Enterprise contribution to NA revenue miss
    >
Enterprise contribution from other segments
```

It says:

**Pipeline coverage is 3.2x.**

That implies a metric:

```text
Open Pipeline / Remaining Plan ≈ 3.2
```

It says:

**Conversion is below LQ and rolling 4Q.**

Now the model needs historical time-series data and definitions for:

```text
Current conversion
Last-quarter conversion
Trailing-four-quarter conversion
```

And the generated data must satisfy:

```text
Current conversion < Last-quarter conversion

Current conversion < Rolling-4Q conversion
```

Finally, it says:

**Two Enterprise reps left, causing sales activity to decline.**

This introduces a causal relationship:

```text
2 rep attritions
        ↓
fewer active Enterprise reps
        ↓
lower sales activity
        ↓
lower opportunity progression / conversion
        ↓
lower Enterprise revenue
        ↓
North America revenue miss
```

That is not a collection of independent database fields.

It is a **causal business model**.

---

# The Scenario Specification

The system should transform the user's natural-language narrative into a structured internal representation.

For example:

```yaml
scenario:
  objective: >
    Model a North America sales performance deterioration scenario
    where Enterprise underperformance is the primary driver.

  scope:
    geography:
      - North America

    segments:
      - Enterprise
      - Mid-Market
      - SMB

  outcomes:

    - id: na_plan_miss
      metric: revenue
      entity: North America
      condition: actual < plan
      severity: material

    - id: na_revenue_decline
      metric: revenue
      entity: North America
      condition: declining
      comparison: prior_period

    - id: enterprise_driver
      metric: revenue
      entity: Enterprise
      condition: primary_driver_of
      target: na_plan_miss

    - id: pipeline_coverage
      metric: pipeline_coverage
      entity: Enterprise
      target: 3.2
      tolerance: 0.1

    - id: conversion_decline
      metric: win_rate
      entity: Enterprise
      condition:
        - below: prior_quarter
        - below: rolling_4_quarter

    - id: activity_decline
      metric: sales_activity
      entity: Enterprise
      condition: declining

  events:

    - type: rep_attrition
      entity: Enterprise
      count: 2

  causal_relationships:

    - cause: enterprise_rep_attrition
      effect: enterprise_sales_activity
      direction: negative

    - cause: enterprise_sales_activity
      effect: enterprise_conversion
      direction: negative

    - cause: enterprise_conversion
      effect: enterprise_revenue
      direction: negative

    - cause: enterprise_revenue
      effect: na_plan_miss
      direction: negative
```

The user never needs to see or write this.

The system generates it.

This becomes the **semantic contract** between the user and the data-generation engine.

---

# Facts, Hypotheses, and Assumptions

One important distinction is that not everything in a business narrative has the same level of certainty.

Some things are explicit facts or requirements.

For example:

```text
Two Enterprise reps left.
Pipeline coverage is 3.2x.
```

Those should become relatively hard constraints.

Other statements are directional:

```text
Revenue is declining.
Sales activity is declining.
Conversion is deteriorating.
```

These should become soft or statistical constraints rather than exact numbers.

And some statements are causal hypotheses:

```text
Rep attrition caused activity decline.
Activity decline contributed to conversion decline.
```

These need to be represented as relationships in the scenario model.

The system therefore needs to distinguish between:

### Hard constraints

```text
Enterprise rep attrition = exactly 2

Pipeline coverage ≈ 3.2x
```

### Directional constraints

```text
Revenue is declining

Activity is declining

Conversion is deteriorating
```

### Relative constraints

```text
Enterprise is the primary driver of the NA revenue miss
```

### Temporal constraints

```text
Attrition occurs before activity decline

Activity decline precedes conversion deterioration

Conversion deterioration contributes to revenue decline
```

This distinction prevents the generator from turning every phrase into an arbitrary hard-coded number.

---

# Assumptions Should Be Explicit

Business narratives almost always contain ambiguity.

In the example, the user has not specified:

* What period is “current”?
* What exactly does “conversion” mean?
* What does LQ mean?
* What is the definition of rolling 4Q?
* How is pipeline coverage calculated?
* How large should the activity decline be?
* How much of the revenue miss should Enterprise explain?

The system should not silently invent all of these.

Instead, it should create an assumptions layer.

For example:

```yaml
assumptions:
  timeframe:
    current_period: 2025-Q4
    history: 6 quarters

  conversion_definition:
    opportunity_win_rate_by_count

  pipeline_coverage_definition:
    open_pipeline / remaining_quota

  lq:
    previous_quarter

  rolling_4q:
    average_of_previous_four_completed_quarters

  attrition_effect:
    enterprise_activity_decline: 10-20%

  enterprise_driver:
    minimum_share_of_na_revenue_miss: 60%
```

The user can accept these assumptions or modify them.

This is much better than asking the user twenty questions before generating anything.

---

# The User Experience Should Stay Simple

The complexity should exist **inside the system**, not in the user's workflow.

The user should be able to write:

> NA missed plan and revenue declining driven by miss in Enterprise segment. Pipeline coverage is strong at 3.2x but conversion is below LQ and rolling 4q. There is a trend in sales activity declining due to rep attrition (2) in Enterprise.

The system should respond with an interpretation such as:

> **Here's what I understood**
>
> North America is experiencing a revenue deterioration, with Enterprise as the primary driver of the miss.
>
> * NA revenue is below plan.
> * Revenue is trending downward.
> * Enterprise accounts for the majority of the miss.
> * Enterprise pipeline coverage is approximately 3.2x.
> * Enterprise conversion is below both last quarter and trailing-four-quarter performance.
> * Two Enterprise reps have left.
> * Sales activity declines following the attrition.
> * The scenario models a causal progression from reduced sales capacity to activity decline, conversion deterioration, and ultimately revenue pressure.

Then the system can show a simple causal chain:

```text
2 Enterprise rep attritions
          ↓
Reduced sales capacity
          ↓
Sales activity declines
          ↓
Conversion deteriorates
          ↓
Enterprise revenue declines
          ↓
North America misses plan
```

The user can simply click:

**Generate dataset**

The user does not need to understand the underlying schema.

---

# The Scenario Should Drive the Schema

This is one of the most important consequences of this architecture.

Today, an LLM might see “sales pipeline” and arbitrarily create:

```text
leads
opportunities
deals
sales_activities
sales_representatives
products
```

This is exactly how we ended up with the confusing `deals` and `opportunities` duplication.

The correct question is not:

> “What tables are normally found in a CRM?”

The correct question is:

> “What entities and relationships are required to make this scenario observable?”

For the example, the system may determine that it needs:

```text
sales_representatives
rep_assignments
segments
regions
opportunities
opportunity_stage_history
sales_activities
revenue
revenue_targets
```

It may also need:

```text
rep_events
```

to represent attrition explicitly.

And if conversion needs to be measured accurately over time, it may require opportunity stage history rather than simply storing the current stage.

The scenario therefore **drives the data model**.

The database schema becomes an implementation detail of the business scenario.

---

# From Scenario to Data Generation

Once the Scenario Specification exists, the generator can construct the dataset around it.

Instead of saying:

> Generate 100,000 realistic opportunities.

the system says:

> Generate a sales organization and opportunity history that satisfies the scenario constraints while maintaining realistic statistical behavior.

The generation process can then proceed through dependencies.

For example:

```text
Organization
     ↓
Regions / Segments
     ↓
Sales Reps
     ↓
Rep Assignments
     ↓
Rep Attrition Events
     ↓
Sales Activities
     ↓
Opportunities
     ↓
Opportunity Progression
     ↓
Conversion
     ↓
Revenue
     ↓
Revenue vs Plan
```

This is much more powerful than generating each table independently.

---

# Business Realism vs Statistical Realism

This distinction is fundamental.

There are two kinds of realism in synthetic data.

## Statistical realism

The individual distributions look plausible.

For example:

```text
Most opportunities are relatively small.

Some opportunities are large.

Reps have a reasonable number of activities.

Opportunity stages follow plausible distributions.
```

This produces data that looks like CRM data.

But it doesn't necessarily behave like a real business.

## Business realism

The data exhibits meaningful relationships.

For example:

```text
Rep attrition
      ↓
Lower activity
      ↓
Lower opportunity progression
      ↓
Lower conversion
      ↓
Lower bookings
      ↓
Revenue miss
```

The most valuable scenario datasets need **both**.

The distributions need to look realistic, but the relationships between them need to tell a coherent business story.

---

# Scenario Invariants

The Scenario Specification should eventually produce a set of **invariants**.

An invariant is something that must be true after generation.

For the example:

```text
1. NA actual revenue < NA revenue plan.

2. NA revenue exhibits a declining trend.

3. Enterprise is the primary contributor to the NA revenue miss.

4. Enterprise pipeline coverage ≈ 3.2x.

5. Current Enterprise conversion < previous-quarter conversion.

6. Current Enterprise conversion < rolling-4Q conversion.

7. Exactly two Enterprise reps leave during the scenario.

8. Enterprise sales activity declines after the attrition event.

9. The activity decline precedes or coincides with conversion deterioration.

10. Enterprise deterioration explains a material portion
    of the overall NA revenue miss.
```

These become the tests against which the generated dataset is evaluated.

---

# Validation Is Not Optional

This is probably the biggest difference between ordinary synthetic-data generation and scenario-driven generation.

The system should never assume:

> “The LLM generated the data, therefore the scenario is represented.”

It should test it.

Suppose the generator produces:

```text
Enterprise reps:
20 → 18

Enterprise activity:
-1.2%

Pipeline coverage:
2.4x

Enterprise contribution to NA miss:
12%
```

Technically, the data contains all the requested concepts.

But the scenario has failed.

The validator should say:

```text
FAILED

Pipeline coverage:
Observed: 2.4x
Required: 3.2x ± 0.1

Enterprise driver:
Observed contribution to NA miss: 12%
Required: primary driver

Activity decline:
Observed: -1.2%
Expected: meaningful decline following attrition
```

The system then regenerates or adjusts the data.

This creates a loop:

```text
Generate
   ↓
Validate
   ↓
Pass? ── Yes ──→ Dataset
   │
   No
   ↓
Adjust / Regenerate
   ↓
Validate again
```

This is what allows the system to produce data that **actually satisfies the user's scenario** rather than merely mentioning its vocabulary.

---

# The Scenario Is an Executable Business Hypothesis

At this point, the Scenario Specification becomes more than documentation.

It is an executable representation of a business hypothesis.

The user is essentially saying:

> “I believe the organization looks like this.”

The system constructs a synthetic world where that hypothesis is true.

For example:

```text
                 Rep Attrition
                       │
                       ▼
                Active Reps ↓
                       │
                       ▼
               Activity ↓
                       │
                       ▼
              Conversion ↓
                       │
                       ▼
              Enterprise Revenue ↓
                       │
                       ▼
                NA Revenue ↓
                       │
                       ▼
                  Plan Miss
```

At the same time:

```text
Open Pipeline
      │
      ▼
   3.2x coverage
```

This creates an interesting business situation:

> Pipeline looks healthy, but the organization is failing to convert it.

That is much closer to how an analyst, sales leader, or executive actually thinks about the problem.

---

# The Scenario DSL

Eventually, this semantic layer could become a small internal domain-specific language.

For example:

```yaml
scenario:

  scope:
    geography: North America
    segment: Enterprise

  period:
    current: 2025-Q4
    history: 4 quarters

  metrics:

    revenue:
      condition: declining
      target: below_plan

    pipeline_coverage:
      value: 3.2
      tolerance: 0.1

    conversion:
      conditions:
        - below: last_quarter
        - below: rolling_4q

    sales_activity:
      condition: declining

  events:

    rep_attrition:
      count: 2
      segment: Enterprise

  relationships:

    - activity <- rep_attrition
    - conversion <- activity
    - revenue <- conversion

  attribution:

    enterprise:
      role: primary_driver
      of: na_revenue_miss
```

The user doesn't need to see this representation.

But the system needs something like it.

The LLM's job is to translate natural language into this structure.

The data-generation engine's job is to translate this structure into data.

That separation is powerful.

---

# The Bigger Architectural Picture

The complete system can therefore look like this:

```text
                         USER
                           │
                           │
                           │ Natural language
                           ▼
                ┌──────────────────────┐
                │ Scenario Interpreter │
                └──────────┬───────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │   Scenario Model     │
                │                      │
                │  Entities            │
                │  Metrics             │
                │  Dimensions          │
                │  Events              │
                │  Relationships       │
                │  Causal links        │
                │  Assumptions         │
                │  Constraints         │
                │  Invariants          │
                └──────────┬───────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │    Schema Planner    │
                └──────────┬───────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │    Data Generator    │
                └──────────┬───────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │ Scenario Validator   │
                └──────────┬───────────┘
                           │
                    ┌──────┴──────┐
                    │             │
                   PASS          FAIL
                    │             │
                    ▼             │
                Dataset      Regenerate
```

The **Scenario Model** is the central artifact.

It is effectively the equivalent of a PRD, but for a synthetic business world.

---

# The Deeper Product Idea

This leads to a broader realization.

The product isn't really just a **synthetic data generator**.

It is closer to:

> **Business Scenario → Executable Data Model**

The user brings a story.

The system extracts the business logic from that story.

It determines what entities, metrics, relationships, historical states, and events are required.

It creates a synthetic organization in which those relationships actually exist.

And finally, it validates that the generated data tells the story the user originally described.

That distinction matters enormously.

A traditional synthetic-data generator asks:

> “What should realistic CRM data look like?”

A scenario-driven generator asks:

> “What would a realistic CRM dataset look like **if this business situation were true?**”

The first generates plausible data.

The second generates **explainable business worlds**.

And that is probably the layer that was missing all along.
