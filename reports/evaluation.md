# Governed self-service analytics — evaluation evidence

Agentic where reasoning helps. Deterministic where correctness matters.

Models propose; deterministic components authorize, execute, and render.

Model: `gpt-5`
Generated: `2026-08-16T21:40:13Z`

## Result

| Evaluation layer | Result |
| --- | ---: |
| Deterministic / local | **16 / 16** |
| Live GPT-5 evaluations | **5 / 5** |
| Executed evaluation cases | **21 / 21** |

Live cases execute the real agent workflow and compare returned analytical rows and visualization semantics against independently computed deterministic references.

Evaluated against executable references, not judged by screenshots.

## Category results

| Category | Passed |
| --- | ---: |
| Analysis correctness | 7 / 7 |
| Visualization semantics | 3 / 3 |
| Governance & security | 4 / 4 |
| Robustness | 2 / 2 |
| Database generalization | 5 / 5 |

## Cases

| Case | Database | Type | Execution | Expected | Result | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Top-k revenue reference | Chinook | Analysis correctness | deterministic/local | Reference top-five country revenue | passed | PASS |
| Temporal and genre references | Chinook | Analysis correctness | deterministic/local | Bounded temporal and multi-table genre revenue | passed | PASS |
| Ranking and distribution lenses | Fixture | Analysis correctness | deterministic/local | Requested lens controls analysis semantics | passed | PASS |
| Lens conflict | Fixture | Analysis correctness | deterministic/local | Conflicting explicit lens is rejected before SQL | passed | PASS |
| Categorical chart semantics | Fixture | Visualization semantics | deterministic/local | Auto and explicit entity labels remain distinct | passed | PASS |
| Post-analysis chart override | Fixture | Visualization semantics | deterministic/local | Revisualization reuses analysis without SQL rerun | passed | PASS |
| Custom visualization boundary | Fixture | Visualization semantics | deterministic/local | Supported chart works; unsupported chart is explicit | passed | PASS |
| Authorization boundary | Fixture | Governance & security | deterministic/local | Denied user reaches no schema, agent, or query | passed | PASS |
| Read-only request block | Fixture | Governance & security | deterministic/local | Mutation request is blocked before agent work | passed | PASS |
| Restricted-column policy | Sakila-shaped fixture | Governance & security | deterministic/local | Hidden fields and table-scoped wildcards are governed | passed | PASS |
| Bounded result and safe audit | Fixture | Governance & security | deterministic/local | Result cap and audit metadata protection | passed | PASS |
| Typed failure outcomes | Fixture | Robustness | deterministic/local | No data, unsupported, and blocked remain distinct | passed | PASS |
| Bounded SQL repair | Fixture | Robustness | deterministic/local | Exactly one repair; a second failure stops | passed | PASS |
| Dynamic onboarding | Sakila-shaped fixture | Database generalization | deterministic/local | Catalog/register/grant are configuration-driven | passed | PASS |
| Supplied Sakila reference | Sakila | Database generalization | deterministic/local | Real category-revenue reference is available | passed | PASS |
| Northwind declared-relationship boundary | Northwind | Database generalization | deterministic/local | Zero declared foreign keys is cataloged faithfully | passed | PASS |
| Chinook top revenue countries | Chinook | Analysis correctness | live GPT-5 | Reference rows and bar semantics | Analysis rows and chart semantics match the deterministic revenue reference | PASS |
| Chinook temporal revenue | Chinook | Analysis correctness | live GPT-5 | Reference rows and line semantics | Analysis rows and chart semantics match the deterministic temporal revenue reference | PASS |
| Chinook genre revenue | Chinook | Analysis correctness | live GPT-5 | Reference rows and bar semantics | Analysis rows and chart semantics match the deterministic genre revenue reference | PASS |
| Northwind category revenue | Northwind | Database generalization | live GPT-5 | Reference rows across undeclared relationships | Analysis rows and chart semantics match the deterministic Northwind category revenue reference | PASS |
| Sakila category revenue | Sakila | Database generalization | live GPT-5 | Reference rows and bar semantics after temporary onboarding | Analysis rows and chart semantics match the deterministic Sakila category revenue reference | PASS |

## Current limitation

Complex multi-objective questions may require decomposition into multiple analytical runs. Predictive concepts such as churn also require an explicit target/definition before analysis.

## Scope of evidence

These benchmarks demonstrate correctness on the supplied databases and representative governance and failure paths; they are not a claim of universal natural-language-to-SQL accuracy.
