# SynGen — One-Pager

## What

SynGen is an AI-native harness that turns a plain-language business story into a realistic synthetic dataset — **with mathematical proof that the data actually tells that story**.

An analyst writes: *"SMB beat plan by 4%, but discounts crept up and margins eroded."* SynGen designs the dataset, generates it, tests every claim against the finished file, and delivers the workbook together with a validation report showing each claim passing. If a claim can't be met, it says so precisely instead of producing quietly wrong data.

One worked example (revenue-operations flavor): a story about quota attainment, discount trends, product-mix shifts and stale pipeline becomes four linked tables — accounts, opportunities, products, quota plan — plus a report where each narrative claim is a checked criterion with a numeric margin of safety.

## Why

Analytics teams are stuck between two bad options:

1. **Real data** — slow to obtain, gated by privacy, and legally frozen in shape. Every new analytics idea waits on data governance.
2. **Traditional synthetic data** — random numbers that look plausible but don't demonstrably encode any specific business narrative, so demos, training, and tooling built on them prove nothing.

SynGen removes the gap: **story-in, provable dataset-out**, on demand, at zero privacy risk. The same story always regenerates the same data (deterministic seeds), so results are reproducible and auditable.

## How

A four-phase pipeline with deterministic machinery doing the heavy lifting and AI doing the translation:

- **Understand** — an LLM converts the story into measurable acceptance criteria; a human approves them at a gate.
- **Design & calibrate** — an LLM drafts a declarative generation config; a deterministic pre-flight layer then *solves* the arithmetic exactly (levels, mixes, plans) rather than hoping the draft guessed well.
- **Generate** — a fixed, versioned engine produces the tables from config alone. No generated code is ever executed.
- **Prove & deliver** — a black-box validator re-derives every criterion from the workbook itself. A convergence loop adjusts knobs until all criteria pass or escalates honestly.

The result: a system where adding capability means adding a small, tested building block — not patching special cases — and where "the data is wrong" is answerable with a validation report instead of a debugging session.

*Status: work in progress, progressing well.*
