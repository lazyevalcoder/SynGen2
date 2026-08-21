# Narrative Matrix — A Better Enterprise Dashboard

> **Design principle:** Don't arrange metrics according to the data model. Arrange them according to the story a human needs to understand.

The dashboard is a **single analytical matrix**.

- **Columns** = business dimensions (Region, BU, Channel, Customer Tier, etc.)
- **Rows** = questions the business naturally asks
- **Row groups** = narrative chapters
- **Cells** = observations
- **Color / delta / sparklines** = signal
- **Order** = intended eye movement

The goal is not to show everything.

The goal is to make the business story visible in one scan.

---

## Example: Regional Business Review

| Narrative | Metric | APAC | EMEA | Americas | Global |
|---|---|---:|---:|---:|---:|
| **OUTCOME** | | | | | |
| | Revenue | **$82M** 🔴 | **$118M** 🟢 | **$214M** 🟢 | **$414M** 🟢 |
| | Revenue growth YoY | **-8.4%** 🔴 | **+4.2%** 🟢 | **+7.8%** 🟢 | **+2.9%** 🟡 |
| | Gross margin | **31.2%** 🔴 | **38.8%** 🟢 | **41.7%** 🟢 | **38.2%** 🟢 |
| **CUSTOMER HEALTH** | | | | | |
| | Churn | **6.2%** 🔴 | 4.1% 🟡 | **2.8%** 🟢 | 4.0% 🟡 |
| | Net revenue retention | **91%** 🔴 | 104% 🟢 | **108%** 🟢 | 101% 🟡 |
| | Customer growth | **-2.1%** 🔴 | +3.4% 🟢 | +5.8% 🟢 | +2.8% 🟢 |
| **GROWTH DRIVERS** | | | | | |
| | Enterprise revenue growth | +2.3% 🟡 | **+8.1%** 🟢 | **+11.4%** 🟢 | +7.4% 🟢 |
| | SMB revenue growth | **-14.6%** 🔴 | +0.8% 🟡 | +4.7% 🟢 | **-2.9%** 🔴 |
| | New business growth | -5.2% 🔴 | +6.8% 🟢 | +9.1% 🟢 | +4.7% 🟢 |
| | Expansion growth | -3.8% 🔴 | +4.2% 🟢 | +7.6% 🟢 | +3.9% 🟢 |
| **PRODUCT** | | | | | |
| | Product A revenue growth | **-18.3%** 🔴 | +5.9% 🟢 | +9.4% 🟢 | +1.2% 🟡 |
| | Product B revenue growth | +4.8% 🟢 | **+8.3%** 🟢 | +2.1% 🟡 | +4.6% 🟢 |
| | Product C revenue growth | **-9.7%** 🔴 | -1.2% 🟡 | +3.8% 🟢 | -1.0% 🟡 |
| **EXCEPTIONS / WATCHLIST** | | | | | |
| | APAC SMB churn | **9.4%** 🔴 | — | — | — |
| | APAC Product A retention | **84%** 🔴 | — | — | — |
| | EMEA Enterprise pipeline | — | **+22%** 🟢 | — | — |
| | Americas margin expansion | — | — | **+320 bps** 🟢 | — |

---

## How the story emerges

### 1. What happened?

**APAC revenue is down 8.4%.**

The other regions are growing.

So the problem is geographically concentrated.

### 2. Is this a healthy business?

APAC has:

- 6.2% churn
- 91% NRR
- -2.1% customer growth

The problem isn't simply a temporary revenue fluctuation.

**Customer health is deteriorating.**

### 3. What's driving the decline?

Scan the growth-driver rows.

Enterprise is roughly stable.

SMB is **-14.6%**.

New business and expansion are both negative.

The eye can immediately infer:

> **APAC's problem is disproportionately an SMB problem.**

### 4. What explains the SMB problem?

Move into Product.

Product A is **-18.3%** in APAC.

Product B is growing.

Product C is declining moderately.

Now the story becomes:

> **APAC revenue is declining because SMB is shrinking, with Product A showing the strongest product-level deterioration.**

### 5. What deserves investigation?

The final section surfaces the **exceptions that deserve human attention**.

APAC SMB churn at 9.4% and Product A retention at 84% are obvious candidates.

---

## The key design rule

The rows should form a **logical chain**:

**OUTCOME**

↓

**CUSTOMER HEALTH**

↓

**GROWTH DRIVERS**

↓

**SEGMENTS**

↓

**PRODUCT**

↓

**EXCEPTIONS**

The reader should progressively move from:

**What happened?**

→ **Is it structural?**

→ **Where is it happening?**

→ **Who is driving it?**

→ **What is causing it?**

→ **What should I investigate?**

That is the narrative.

The dashboard does not need a chatbot to explain it.

**The arrangement of the information explains it.**

---

## Visual design principles

### 1. The matrix is the primary visualization

Don't surround it with 15 KPI cards.

Don't turn every metric into a chart.

The **grid itself is the visualization**.

### 2. Not every cell needs equal visual weight

Primary metrics:

**-8.4%**

Supporting metrics:

91%

Context:

↓ 2.1%

Use typography, whitespace, indentation and subtle color to establish hierarchy.

### 3. Color means signal

Use color sparingly.

- 🟢 Positive
- 🟡 Watch
- 🔴 Negative
- Neutral = no meaningful signal

Color should help the eye find the story, not turn the dashboard into a Christmas tree.

### 4. The columns should remain stable

If the columns are regions, keep regions in the same position.

This lets the reader build visual memory:

> "APAC is the red column."

Patterns become recognizable almost subconsciously.

### 5. The rows should be deliberately ordered

Do **not** order metrics alphabetically.

Do **not** order them according to the database schema.

Do **not** give every stakeholder-requested KPI equal importance.

Order them according to the **investigative journey**.

---

## The deeper idea

A conventional dashboard asks:

> **"What data should we display?"**

A Narrative Matrix asks:

> **"What should the human understand after looking at this?"**

That changes everything.

The metrics become the vocabulary.

The rows become the questions.

The columns become the dimensions.

The visual hierarchy becomes the grammar.

And the entire matrix becomes a **visual argument about the state of the business**.

> **Don't build dashboards. Build visual narratives out of structured data.**
