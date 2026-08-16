# Governed self-service analytics

Governed self-service analytics with autonomous reasoning: two connected AI agents turn a natural-language question into governed SQL analysis, a validated analytical result, and a deterministic visualization—using only databases the requesting user is authorized to access.

> Agentic where reasoning helps. Deterministic where correctness matters.

## Evidence at a glance

- **92 automated tests passed; 1 intentionally skipped** (the live-agent pytest placeholder)
- **16 / 16 deterministic evaluations**
- **5 / 5 live GPT-5 evaluations**
- Runtime database onboarding with schema discovery, registration, and grants

## How it works

Streamlit is the interactive product surface. The developer CLI provides operational tooling for database onboarding, evaluation, verification, and reproducible demo-state management. The governed Analytics Service remains the application core behind the interactive analysis workflow:

```text
Streamlit
        ↓
Analytics Service
        ↓
Deterministic Coordinator
        ↓
ACL / Governance
        ↓
Analysis Agent
        ↓
SQL Proposal
        ↓
Read-only SQL Executor
        ↓
AnalysisResult
        ↓
Visualization Agent
        ↓
ChartSpec
        ↓
Deterministic Renderer
```

Authorization happens before schema access, model invocation, or query execution. The Analysis Agent reasons over the authorized schema and proposes SQL; the coordinator owns execution order, failure handling, and the one-repair budget. A failed SQL proposal can receive at most one coordinator-approved repair. The SQL Executor returns a bounded `QueryResult`, which `AnalysisAgent.summarize()` turns into the validated analytical `AnalysisResult` consumed downstream. The Visualization Agent receives only that completed result—never a database connection or SQL tool—and returns a typed `ChartSpec`. Deterministic rendering executes no model-generated plotting code.

> Models propose; deterministic components authorize, execute, and render.

## Governed by design

- Backend ACL enforcement before schema or agent work
- Read-only SQLite execution with unsafe SQL rejection
- Restricted-column governance, including table-scoped wildcard protection
- Configurable bounded result sets (500 rows in the supplied configuration)
- At most one SQL repair attempt
- Typed `success`, `no_data`, `unsupported`, and `blocked` outcomes
- Safe `ALLOWED` / `DENIED` audit activity without credentials or result rows
- Generated SQL, schema provenance, repairs, bounds, and run status visible in Run Details

## Evaluation

The evaluation suite separates deterministic evidence from billable model-backed evidence:

| Layer | Result | How it runs |
| --- | ---: | --- |
| Automated tests | **92 passed, 1 intentionally skipped** | `pytest`; no OpenAI calls |
| Deterministic evaluation | **16 / 16** | `analytics eval local`; executable reference cases |
| Live GPT-5 evaluation | **5 / 5** | `analytics eval live`; five real agent workflows |

Live cases compare returned analytical rows and visualization semantics against independently computed deterministic references.

> Evaluated against executable references, not judged by screenshots.

### Generate the evaluation report

```bash
.venv/bin/analytics eval local
```

This runs the selected deterministic cases without API usage and writes `reports/evaluation.json` and `reports/evaluation.md`.

```bash
.venv/bin/analytics eval live
```

This intentionally runs the five live GPT-5 benchmark cases, temporarily onboards Sakila for its case, updates the same report outputs, and restores the canonical pre-demo state afterward. It may use API credits.

The `agent_eval` pytest marker currently contains an intentionally skipped placeholder; it is not the five-case live benchmark. Use `analytics eval live` for that benchmark.

## Dynamic database onboarding

> Same core. New database. No database-specific application code.

```bash
.venv/bin/analytics db add \
  --name sakila \
  --path datasets/sakila.db \
  --grant donne
```

The command validates a read-only SQLite connection, introspects tables, columns, keys, and relationships, writes generated catalog metadata, registers the source, and grants it to Donné. No Sakila-specific analysis or visualization code is added.

Canonical demo state before the signature onboarding moment:

```text
Toyesh  → Chinook, Northwind
Alfred  → Chinook
Donné   → no sources
Sakila  → unregistered
```

Generate catalogs for supplied databases without changing registry or ACL state:

```bash
.venv/bin/analytics db catalog --name chinook --path datasets/chinook.db
.venv/bin/analytics db catalog --name northwind --path datasets/northwind_small.sqlite
```

Check or restore the canonical demo state:

```bash
.venv/bin/analytics demo check
.venv/bin/analytics demo reset
```

## Run locally

The supplied OpenAI key belongs only in an untracked local `.env` file. The SDK reads `OPENAI_API_KEY` from the environment; it is never hardcoded, displayed, logged, or committed.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env  # add the supplied key locally; never commit .env
.venv/bin/streamlit run app.py
```

Without an API key, deterministic tests, onboarding, ACL checks, SQL safety, and rendering remain usable. A live analysis attempt reports a clean configuration error instead of using a fake key.

## Tests and targeted verification

Run the deterministic suite:

```bash
PYTHONPATH=src .venv/bin/python -m pytest
```

The following commands intentionally make real model calls and compare their results with deterministic references:

```bash
.venv/bin/analytics verify chinook-revenue
.venv/bin/analytics verify chinook-temporal
.venv/bin/analytics verify chinook-genres
```

## Limitations and production evolution

Complex multi-objective questions may require decomposition into multiple analytical runs. Predictive concepts such as churn require an explicit target and definition before analysis.

| Today | Production evolution |
| --- | --- |
| SQLite | PostgreSQL / warehouse adapters |
| Demo personas | Identity + centralized RBAC |
| UI + CLI | API / MCP exposure |
| Run telemetry | Full tracing, token, and cost telemetry |

The production column is an architectural direction, not functionality claimed as implemented here.
