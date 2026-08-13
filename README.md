# Governed Analytics Command Center

Two connected AI agents for controlled SQLite analysis and visualization.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env  # add supplied key locally; never commit this file
.venv/bin/streamlit run app.py
```

## Onboard Sakila for Donné

```bash
.venv/bin/analytics db add --name sakila --path datasets/sakila.db --grant donne
```

The command validates a read-only SQLite connection, captures tables/columns/PKs/FKs in `catalogs/sakila.json`, registers the database, and grants access without source-code changes.

## Generate supplied-data catalogs without changing the demo

```bash
.venv/bin/analytics db catalog --name chinook --path datasets/chinook.db
.venv/bin/analytics db catalog --name northwind --path datasets/northwind_small.sqlite
.venv/bin/analytics demo check
```

After an onboarding rehearsal, restore the canonical pre-demo state with:

```bash
.venv/bin/analytics demo reset
```

## Tests

```bash
PYTHONPATH=src python3 -m pytest
PYTHONPATH=src python3 -m pytest -m agent_eval
```

The default suite never invokes OpenAI. Live agent evaluations require both `OPENAI_API_KEY` and downloaded assignment datasets.

## One verified live Chinook run

This command intentionally invokes the configured OpenAI model and can use API credits. It asks a fixed,
simple aggregation question, then compares the agent's returned data and visualization semantics against
an independent deterministic reference query.

```bash
.venv/bin/analytics verify chinook-revenue
```

The next two vertical cases are intentionally separate because they exercise different analytical
capabilities and make real model calls:

```bash
.venv/bin/analytics verify chinook-temporal
.venv/bin/analytics verify chinook-genres
```
