# Synthetic Business Dataset Generation Framework

## 📖 Overview
A structured, objective framework for generating high-quality synthetic datasets for business domains. Built around measurable criteria, enforceable benchmarks, and repeatable rules. Designed for hybrid LLM + statistical generation pipelines.

---

## 📐 Core Criteria, Benchmarks & Rules

| Dimension | Criterion | Benchmark / Threshold | Rule |
|-----------|-----------|------------------------|------|
| **Statistical Fidelity** | Marginal & joint distributions match source | KS test `p > 0.05`, correlation matrix error `<5%`, tail behavior preserved | Use distribution-aware generation (Copulas, CTGAN, SDV, or parametric sampling). Never assume uniformity. |
| **Business Logic Compliance** | Hard/soft constraints enforced | `100%` hard rule pass, `<1%` soft rule violations (with explainable fallbacks) | Define all constraints *before* generation. Validate post-generation with automated checks. |
| **Privacy & Security** | No PII leakage or re-identification risk | Zero exact matches to real records, `k ≥ 5` anonymity, re-ID risk `<0.1%` | Strip direct identifiers, apply DP noise or k-anonymity where needed, avoid preserving rare combos. |
| **Analytical Utility** | Downstream tasks perform within tolerance | Model metric drop `<5%`, KPI drift `<2%`, edge cases preserved | Align generation scope to use case (ML training vs. BI testing vs. compliance). Don't over-smooth. |
| **Reproducibility & Governance** | Deterministic, versioned, auditable | Identical output on re-run (seeded), full lineage, schema registered | Code-driven generation. Config-only parameters. Seed control. Schema validation (Great Expectations/Pandera). |
| **Scalability & Performance** | Predictable time/storage scaling | Linear scaling with record count, `<2x` memory overhead, Parquet/Arrow output | Batch generation. Use efficient dtypes. Avoid over-normalization or redundant joins. |

---

## 🤖 LLM Reality Check & Hybrid Architecture

- **Strengths**: Schema design, constraint drafting, text generation, documentation, prompt engineering
- **Weaknesses**: Poor numerical/statistical fidelity, correlation drift, uniform distribution bias, hard constraint violations
- **Recommended Architecture**:
  1. **LLM Layer**: Draft schema, business rules, validation logic, sample templates, documentation
  2. **Statistical/Programmatic Layer**: Execute generation with seeded RNG, constraint injection, distribution fitting
  3. **Validation Layer**: Automated checks against benchmarks above
- **Rule**: Never rely on LLMs alone for numerical or relational fidelity. Use them as architects, not engines.

---

## 🔄 Standardized Generation Workflow

1. **Define Use Case & Success Metrics** → ML training, BI testing, compliance, performance benchmark? Sets tolerance thresholds.
2. **Extract Constraints from Real Data** → Distributions, FK relationships, business rules, date logic, probability mappings, quota math.
3. **Choose Generation Engine** → `Faker` + `pandas` + `numpy` (simple), `SDV`/`CTGAN`/`Copulas` (complex/ML), LLM-augmented for rules/schema.
4. **Generate with Seeded RNG & External Config** → All parameters externalized. Deterministic by design.
5. **Validate Against Benchmarks** → Automated statistical tests, constraint checks, privacy audit, utility benchmark.
6. **Package & Version** → Output format (Parquet/CSV), metadata JSON, schema registry, lineage log, seed hash.

---

## 📏 Benchmark Calculation & Acceptance Thresholds

| Benchmark Type | How to Calculate | Acceptance Threshold |
|----------------|------------------|----------------------|
| Distribution Match | Kolmogorov-Smirnov / Chi-square on key columns | `p > 0.05` or `Δ < 0.05` |
| Correlation Fidelity | Pearson/Spearman matrix diff vs source | `max(|Δ|) < 0.05` |
| Constraint Pass Rate | `count(valid) / count(total)` on rule engine | `≥ 99%` (hard rules `100%`) |
| Utility Drop | Train baseline model on real vs synthetic → compare AUC/MAE/R² | `Δ < 5%` |
| Privacy Risk | k-anonymity group size, re-ID simulation, exact match count | `k ≥ 5`, `0 exact matches` |
| Determinism | Hash output after re-run with same seed | `identical` |

*Note: Thresholds are starting points. Adjust based on domain sensitivity (e.g., finance/healthcare demand tighter bounds than marketing demos).*

---

## 🎯 Use-Case Priority Matrix

| If your goal is... | Focus on... | De-emphasize... |
|--------------------|-------------|-----------------|
| ML model training | Statistical fidelity, utility, correlation preservation | Perfect business rule compliance |
| BI/Reporting testing | Date logic, hierarchy, constraint pass rate, scalability | Tail distribution accuracy |
| Compliance/Demo | Privacy, zero PII, clean schema, deterministic output | Statistical realism |
| Pipeline/Performance testing | Volume, schema drift, constraint violations, edge cases | Correlation fidelity |

---

## ✅ Implementation Checklist

- [ ] Stages & probabilities explicitly mapped & enforced
- [ ] Coverage target range defined (`1.2x–2.5x`)
- [ ] Rep tiers + quota alignment modeled
- [ ] Date logic supports period-based grouping
- [ ] Validation rules automated
- [ ] Generation script is config-driven & reproducible
- [ ] Output packaged with metadata, schema, and seed hash

---

## 📦 Recommended Tooling Stack

- **Generation**: Python (`pandas`, `numpy`, `scipy.stats`, `Faker`, `SDV`)
- **Validation**: `great_expectations`, `pandera`, or custom SQL/Python checks
- **Storage**: Parquet (compressed, schema-enforced) or CSV for sharing
- **Config/Versioning**: YAML/JSON + Git version control + `pydantic`/`dataclasses` for schema validation
- **LLM Integration**: Prompt for rules/schema → export to JSON → feed to generator script

---

*Framework designed for objective, repeatable, and production-ready synthetic dataset generation. Adjust thresholds based on domain risk tolerance and downstream use case.*
