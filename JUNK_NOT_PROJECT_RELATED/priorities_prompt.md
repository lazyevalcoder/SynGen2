You are a strategy consultant defining a strategic performance measurement framework for a dataset.

SCHEMA:
{schema}

STRUCTURAL KNOWLEDGE GRAPH:
{structural_kg}

DIAGNOSTIC KNOWLEDGE GRAPH:
{diagnostic_kg}

=== YOUR TASK (4 steps) ===

Work through these steps IN ORDER, then return ONE JSON object with everything.

STEP 1 — DECONSTRUCT THE SCHEMA & MAP TO BUSINESS DOMAINS
Infer what business this data represents (sales pipeline, e-commerce, subscription revenue, supply chain, ...). Identify the grain of the data (what does one row represent?), the business entities, the measures, and the dimensions available. This mapping is the foundation for everything below — every indicator and metric you name must be computable from the schema columns.

STEP 2 — HEALTH INDICATORS TABLE (Health Indicator | Why? | Importance)
Enumerate ALL plausible health indicators this data could inform — the meaningful signals a leader would check for this business (e.g., for a pipeline: coverage ratio, stage conversion, velocity, stagnation, forecast accuracy). For each, give a one-line WHY (what it reveals) and an IMPORTANCE (high | medium | low). Then mark `selected: true` on the FEW most important ones that become the focus for the next steps. Every listed indicator must be derivable from the schema columns — no external benchmarks or hypothetical data.

STEP 3 — OUTCOMES + EXECUTIVE QUESTIONS
3.1 Outcomes are the priorities. An OUTCOME is NOT a noun or a metric name — it answers "What are we trying to achieve?" as a verb-phrase goal (e.g., "Build enough qualified pipeline", "Convert pipeline into revenue", "Protect margin as volume scales"). Outcomes must be MECE and, where the business has a natural lifecycle, ordered with a natural flow (upstream → downstream). 3-5 outcomes.
3.2 Executive Questions are the decision-focused questions a leader asks about the outcome — a REASONING LAYER that frames and justifies the metrics. They carry NO metrics themselves. They are decision questions, not metric questions (e.g., "Are we creating enough pipeline?", "Where is pipeline stalling?"). 2-4 per outcome.

STEP 4 — KPIs + OPERATIONAL METRICS + ANALYTICAL LENSES
4.1 KPIs drive actions for each outcome. KPIs emphasize CHANGE (delta) over absolute values — a comparison basis (QoQ, YoY, MoM, vs baseline) that makes "good vs bad" answerable. Expand your thinking on the comparison that makes sense for each measure, not just QoQ/YoY. Few, meaningful, actionable KPIs — do NOT invent metrics for their own sake. 2-5 per outcome.
4.2 Operational Metrics (drivers) answer "Why did the KPI move?" — simple evidence that explains the KPI's movement. 2-5 per KPI.
4.3 Analytical Lenses (optional, 0-3 per KPI) answer "Why does this business behave this way?" — the investigation modes to apply when an anomaly needs deeper analysis. Pick ONLY from the closed catalog below.

=== COMPUTABILITY GATE (apply to EVERY KPI and operational metric before proposing it) ===

A metric either works or it doesn't — no in-betweens. Every KPI and operational metric MUST pass all five tests. If it fails any test, drop it or redefine it in a passing form.

1. SCALAR — `measurement` resolves to ONE number per period, never a per-dimension vector. ("Win Rate by Deal Stage", "each agent's share" are invalid.)
2. COMPUTABLE — every referenced column exists in the schema; no external benchmarks, targets, indices, scores, or hypothetical data.
3. BASELINE — a delta (% change / growth / decline / rate) is ONLY valid when a prior window exists AND the prior value is real and non-zero. If you cannot be confident of a non-zero prior baseline, define the metric at LEVEL (current-period absolute) — or do not define it. NEVER propose a percentage you cannot prove has a baseline. Rule of thumb: when a measure would collapse to "nothing before" (e.g. new-account counts, first-time events), prefer the absolute count.
4. ANCHOR — every counted row must fall inside the resolved time windows (the period is anchored to ONE time column). If the records you count carry no date in that time column (e.g. "active" records that never closed), a period-over-period delta computes to 0 vs 0 and is undefined — define as a LEVEL snapshot or drop it.
5. EXPRESSIBLE — the metric must map to the operator DSL or a single aggregate (count/sum/mean/median/std/count_distinct/ratio/share/topk_share, optional condition; or group/new operator steps). If it cannot be expressed, do not define it.

For EACH proposed metric, you must be able to answer: which schema column? which aggregation? which comparison? what is the prior baseline and can I prove it is real and non-zero? does every counted row fall inside the time windows? If you cannot answer all five, do NOT emit the metric.

=== CONCEPT ONTOLOGY ===

- OUTCOME (a Priority): "What are we trying to achieve?" — a verb-phrase business goal, not a noun. Lives in the priority name + description.
- EXECUTIVE QUESTION: a decision a leader must make about the outcome. Reasoning layer only — frames the metrics, never contains them.
- KPI: a directly measurable indicator that drives action on the outcome. Judged by its DELTA (change/comparison), never a raw level. Stable, recognized business measure (Revenue Growth, Win Rate, Sales Cycle Length, Average Deal Size). Its `measurement` resolves to ONE aggregate scalar.
- OPERATIONAL METRIC (driver): simple evidence for why a KPI moved. Also one scalar, also delta-defined.
- ANALYTICAL LENS: a closed-catalog investigation mode for deeper analysis — NOT a metric, NOT computable by the metric engine. Annotations only.

ANALYTICAL LENS CATALOG (closed — pick only from these):
Trends | Mix shift | Elasticity | Velocity | Cohorts | Causality | Composition

Forbidden:
- An OUTCOME named as a noun or metric ("Revenue Growth" as an outcome name is wrong; "Accelerate revenue growth" is right).
- A KPI or operational metric with no delta/comparison basis in `measurement` (absolute level only).
- A KPI or operational metric whose `measurement` resolves to a per-dimension vector instead of ONE scalar — "Win Rate by Deal Stage", "each agent's share", "per product change" are invalid. A metric is a single line item with one number; dimension breakdowns belong to the scorecard's columns, never in the metric definition.
- Naming a metric after a dimension: "Cycle Time by Product" ✗ → name "Sales Cycle Length", slice by Product in `measurement`.
- Naming a metric after an invented construct or a lens: "Value Optimization Potential" ✗, "Sales Capacity Alignment" ✗ → name the stable measure.
- Defining a metric the schema cannot compute (requires columns not in the schema).
- An `analytical_lenses` value outside the closed catalog.

=== RULES ===

- 3-5 outcomes, ordered with a natural business flow (upstream → downstream) where applicable; MECE — each outcome owns a distinct focus.
- 2-4 executive questions per outcome, decision-focused, MECE, no overlap.
- 2-5 KPIs per outcome; 2-5 operational metrics per KPI; 0-3 analytical lenses per KPI.
- Executive questions are the reasoning layer: they frame the outcome and its metrics. They never contain their own KPI or metric definitions.
- DELTA: every KPI and operational metric must be defined as a change or comparison (period-over-period, YoY/QoQ/MoM, vs baseline, trajectory). Absolute levels do not answer "good or bad?".
- SCALAR: every KPI and operational metric is a single line item — `measurement` resolves to ONE aggregate value, never a per-dimension vector.
- COMPUTABILITY: every KPI and operational metric must pass the FIVE TESTS (SCALAR, COMPUTABLE, BASELINE, ANCHOR, EXPRESSIBLE) above. A metric that fails any test is NOT defined. Never propose a delta without a provable non-zero prior baseline; never propose a period-over-period metric whose rows fall outside the time windows. It either computes or it is honestly not defined — there is no substitution, no degraded version.
- UNIQUENESS: across an outcome, no two metrics apply the same analytical lens to the same business measure.
- ALIGNMENT: an operational metric explains why ITS KPI moved — same business concept, no new concept introduced.
- Use exact column names from the schema for the `metric` field.
- Express the analytical lens (trajectory, momentum, mix, concentration, variance) in `measurement`/`description`, never in the metric name.
- Keep it lean. Few, meaningful, actionable metrics — never pad for structure. An executive should be able to hold the whole framework in their head.

=== OUTPUT FORMAT ===

Return a JSON object:

{
  "domain": "Short phrase: the business domain this data represents",
  "health_indicators": [
    { "name": "Health indicator name", "why": "One line — what it reveals", "importance": "high|medium|low", "selected": true }
  ],
  "priorities": [
    {
      "name": "Outcome as verb phrase — what we are trying to achieve",
      "description": "1 sentence describing the objective in business terms",
      "executive_questions": [
        "Decision-focused executive question 1",
        "Decision-focused executive question 2"
      ],
      "kpis": [
        {
          "name": "KPI name — stable, recognized business measure judged by its delta",
          "metric": "Exact schema column this KPI derives from",
          "description": "1 sentence — what this measures and why it matters",
          "measurement": "Precise business formula with an explicit comparison basis, resolving to ONE scalar",
          "operational_metrics": [
            {
              "name": "Driver name — evidence for why the KPI moved",
              "metric": "Exact schema column this metric derives from",
              "description": "1 sentence — what this evidence reveals",
              "measurement": "Precise business formula with a comparison basis, resolving to ONE scalar"
            }
          ],
          "analytical_lenses": ["Trends", "Mix shift"]
        }
      ]
    }
  ]
}

Return ONLY the JSON object. No other text.
