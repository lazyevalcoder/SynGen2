┌──────────────────────────────────────────────────────────────────────┐
│                         USER / SCENARIO AUTHOR                       │
│                                                                      │
│  													                   │
│   								                                   │
│   									                               │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         1. SCENARIO AGENT                            │
│                                                                      │
│  Understands the narrative and converts it into a formal scenario.  │
│                                                                      │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────┐ │
│  │  Extract    │ │  Interpret   │ │ Formalize    │ │  Assumption │ │
│  │  entities   │ │  narrative   │ │ constraints  │ │  manager    │ │
│  └─────────────┘ └──────────────┘ └──────────────┘ └─────────────┘ │
│                                                                      │
│                         ↓                                            │
│                  SCENARIO SPECIFICATION                              │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    2. SCENARIO / SPEC LAYER                         │
│                                                                      │
│  Canonical machine-readable representation of the scenario.         │
│                                                                      │
│  • Entities & dimensions                                            │
│  • Relationships                                                     │
│  • Measures                                                          │
│  • Time model                                                        │
│  • Distributions                                                     │
│  • Correlations                                                      │
│  • Temporal behavior                                                 │
│  • Business constraints                                              │
│  • Assumptions                                                       │
│  • Validation criteria                                               │
│                                                                      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                          3. HARNESS                                  │
│                                                                      │
│               "Execute the scenario specification"                   │
│                                                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌────────────────────────┐ │
│  │ Schema       │    │ Population   │    │ Relationship            │ │
│  │ Builder      │───▶│ Generator    │───▶│ Generator               │ │
│  └──────────────┘    └──────────────┘    └────────────────────────┘ │
│          │                   │                       │               │
│          └───────────────────┼───────────────────────┘               │
│                              ▼                                       │
│                    ┌──────────────────┐                              │
│                    │ Value / Measure  │                              │
│                    │ Generator        │                              │
│                    └────────┬─────────┘                              │
│                             ▼                                        │
│                    ┌──────────────────┐                              │
│                    │ Temporal         │                              │
│                    │ Simulator        │                              │
│                    └────────┬─────────┘                              │
│                             ▼                                        │
│                    ┌──────────────────┐                              │
│                    │ Constraint       │                              │
│                    │ Engine           │                              │
│                    └────────┬─────────┘                              │
│                             ▼                                        │
│                       SYNTHETIC DATA                                 │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         4. VALIDATION                                │
│                                                                      │
│  Does the data actually tell the story?                              │
│                                                                      │
│  Structural validation     Statistical validation                    │
│  ─────────────────────     ───────────────────────                   │
│  • correct dimensions      • distributions                          │
│  • valid relationships     • correlations                            │
│  • no orphan records       • concentration                           │
│  • referential integrity  • temporal behavior                        │
│                                                                      │
│  Narrative validation                                               │
│  ────────────────────                                               │
│  • top 15% ≈ 40% ARR                                               │
│  • bottom 25% < 50% average opportunity                             │
│  • assignments unchanged                                           │
│  • growth/contraction present                                       │
│                                                                      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                      ┌────────┴─────────┐
                      │                  │
                   PASS                 FAIL
                      │                  │
                      ▼                  ▼
               ┌─────────────┐    ┌──────────────┐
               │   OUTPUT    │    │ Repair /     │
               │   DATASET   │    │ Regenerate   │
               └─────────────┘    └──────┬───────┘
                                         │
                                         └───────► Harness