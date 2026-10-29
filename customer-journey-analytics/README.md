# JourneyIQ Customer Journey Analytics

JourneyIQ combines a deterministic synthetic-data pipeline, PostgreSQL schema, validation/reproducibility reports, automated tests, and Streamlit dashboards. The existing React preview remains a separate 100-session DEMO DATA sample; it is not a substitute for the Python generator or a full-scale verification.

## Windows setup (PowerShell)

Run these commands from the repository root. Python 3.11 is recommended.

```powershell
cd customer-journey-analytics
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
```

The optional PostgreSQL connection setting is shown blank in `.env.example`. For CSV-only use, no database connection is required. Never commit a populated `.env`, password, API key, or database credential.

## Generate data

Starter profile (seed `20261022`, 100 sessions, configured to emit exactly 2,000 events including injected duplicate evidence):

```powershell
python -m yottajourney.pipeline --output data --seed 20261022
```

Configured full profile (100,000 sessions and a 2,000,000-event generation target, including injected duplicate evidence):

```powershell
python -m yottajourney.pipeline --full --output data-full --seed 20261022
```

A custom profile can use `--sessions`, `--customers`, `--chunk-size`, and `--start-date`:

```powershell
python -m yottajourney.pipeline --sessions 250 --customers 180 --chunk-size 5000 --start-date 2026-01-01 --output data-custom --seed 20261022
```

Event rows are serialized through a configurable `--chunk-size` buffer rather than accumulated as millions of Python dictionaries. The generator still loads the canonical event table into a DataFrame for analytics and validation, so end-to-end peak memory is not strictly bounded. Full-scale generation has not been executed/verified in this environment; do not infer that the target counts were produced from the command configuration alone.

Generated output includes CSVs for all ten core entities plus `cart_items` and `experiment_assignments`, a separate `ground_truth.csv`, `validation_report.json`, and `reproducibility.json`.

## Reproducibility verification

Generate the starter profile twice using the same configuration, compare every CSV SHA-256, per-entity row counts, derived metrics, and anomaly counts, and save the comparison in the manifest:

```powershell
python -m yottajourney.pipeline --output data-repro --seed 20261022 --verify-reproducibility
```

The `identical` flag is true only when all compared counts, hashes, metrics, and anomaly counts match. This command writes a second temporary dataset and requires additional time and disk/memory capacity. A paired full-profile verification remains resource-intensive because analytics and validation load the event DataFrame.

## Automated tests

```powershell
python -m pytest -q
```

Run focused generator, relationship, funnel, anomaly, and reproducibility tests:

```powershell
python -m pytest tests/test_pipeline.py -q
```

Run the standalone demo-data tests:

```powershell
python -m pytest tests/test_demo_dashboard_data.py -q
```

## Launch dashboards

Standalone deterministic 100-session DEMO DATA dashboard:

```powershell
python -m streamlit run dashboard/app.py
```

Pipeline-backed dashboard (generate `data/` first):

```powershell
$env:PYTHONPATH = "src"
python -m streamlit run app.py
```

Both Streamlit dashboards provide date, channel, device, and product filters, plus filtered event CSV and JSON downloads. The pipeline-backed dashboard reads the generated profile and reports full source/filtered counts; the standalone dashboard remains an independent synthetic preview.

## Database schema (optional)

The production schema targets PostgreSQL 15+. Create a `journeyiq` database, then apply `schema.sql` and `verify_schema.sql` with your PostgreSQL client. The generator accepts `--database-url` or `DATABASE_URL` and appends into an already-created schema; it does not create or replace tables. `analytics.sql` provides funnel, conversion, mature-cart abandonment, duplicate-conversion, identity-exception, and arrival-order queries.

## Entity and business contracts

The ten required entities are Customer, Session, JourneyEvent, Page, Product, Cart, Order, SupportTicket, Experiment, and JourneyOutcome. CartItem and ExperimentAssignment are relationship tables. See:

- [`docs/data_dictionary.md`](docs/data_dictionary.md) — field contracts and keys for all entities/relationship tables.
- [`docs/relationships.md`](docs/relationships.md) — cardinalities, referential behavior, and ER model.
- [`docs/business_rules.md`](docs/business_rules.md) — consent, session timeout, funnel eligibility, conversion, abandonment, and anomaly policy.
- [`docs/synthetic_data_manifest.md`](docs/synthetic_data_manifest.md) — synthetic source, generation configuration, artifact names, and scale limitations.

Business measures use distinct eligible human funnel-entry sessions; purchase events are not raw conversion counts. Cart abandonment excludes carts that have not yet been idle for the documented 30-minute timeout. Intentional anomaly labels are separate from detector inputs and are not structural integrity failures.

## Verification status and limitations

Source code and tests are present, but this editing environment does not provide a Python runtime, pytest runner, PostgreSQL server, or Streamlit launch facility. Therefore Python tests, generator output, SHA-256 comparisons, SQL execution, and dashboard runtime have **not** been verified here. Full-scale counts have not been generated or checked. See `docs/synthetic_data_manifest.md` for the full-generation memory limitation and use the exact Windows commands above for local verification.
