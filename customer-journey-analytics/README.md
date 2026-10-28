# JourneyIQ · Customer Journey Analytics

JourneyIQ is a reproducible synthetic customer-journey data pipeline, PostgreSQL schema, validation suite, and Streamlit analytics workspace. It preserves raw source events, applies documented session and funnel rules, and separates intentionally injected anomalies from structural integrity validation.

## Environment and commands

Run these from `customer-journey-analytics/`. Install the Python dependencies:

```text
python -m pip install -r requirements.txt
```

Generate the starter profile (seed `20261022`, 100 sessions, approximately 2,000 events):

```text
PYTHONPATH=src python -m yottajourney.pipeline --output data --seed 20261022
```

PowerShell equivalent:

```powershell
$env:PYTHONPATH = "src"
python -m yottajourney.pipeline --output data --seed 20261022
```

Generate the full profile (100,000 sessions, approximately 2,000,000 events):

```text
PYTHONPATH=src python -m yottajourney.pipeline --full --output data-full --seed 20261022
```

PowerShell equivalent:

```powershell
$env:PYTHONPATH = "src"
python -m yottajourney.pipeline --full --output data-full --seed 20261022
```

Override generation dimensions with `--sessions`, `--customers`, `--chunk-size`, and `--start-date`. For example, use `--sessions 250 --customers 180 --chunk-size 5000` for a custom run. `--chunk-size` bounds database insert batches; CSV generation currently materializes the generated tables in memory. The full profile is configured but has **not been performance-verified as a chunked/streaming CSV generator**. Check available memory before requesting the full profile; do not interpret the selected profile as proof that its requested row counts have completed.

Run the complete test suite:

```text
python -m pytest -q
```

Run the deterministic two-output comparison specifically:

```text
python -m pytest tests/test_pipeline.py::test_reproducibility_compares_same_full_profile_and_serialized_datasets -q
```

Launch the standalone DEMO DATA dashboard:

```text
streamlit run dashboard/app.py
```

Launch the dashboard backed by generated CSVs after running the starter generator:

```text
PYTHONPATH=src streamlit run app.py
```

On PowerShell, set `$env:PYTHONPATH = "src"` before launching the pipeline-backed dashboard.

## Data contract and keys

`schema.sql` defines ten required core entities—Customer, Session, JourneyEvent, Page, Product, Cart, Order, SupportTicket, Experiment, JourneyOutcome—and the CartItem and ExperimentAssignment bridge tables. Every entity has a deterministic application-assigned primary key. Foreign keys preserve parentage; nullable customer links represent unlinked identities. Unique constraints include cart/product and experiment/session pairs and one current outcome per session. Lifecycle enums, time intervals, optional relationships, cardinalities, and deletion semantics are documented in [`docs/data_dictionary.md`](docs/data_dictionary.md) and [`docs/relationships.md`](docs/relationships.md).

The generator writes one stable CSV per entity, `ground_truth.csv`, `validation_report.json`, and `reproducibility.json`. Event occurrence and ingestion timestamps are distinct. Event-time ordering represents the journey; ingestion ordering may differ for the injected out-of-order case. The source contract requires each event's ingestion timestamp to be no earlier than its occurrence timestamp.

## Measurement rules

- **Generated rows** are all entity rows emitted for the selected profile. **Filtered rows** are a dashboard subset determined by active date, channel, and device filters. Dashboard filter summaries show both the selected count and the full generated count. Validation and reproducibility manifests explicitly identify full-profile comparisons; a filtered extract is not compared with a full dataset.
- Funnel eligibility is a distinct non-bot session with a `session_started` event after the active filters. Stage counts are distinct eligible sessions reaching each event. Stage-to-stage conversion and drop-off use the preceding stage count; overall conversion is distinct eligible sessions with a paid order divided by eligible funnel-entry sessions.
- Purchase event rows are retained for audit, but order and conversion metrics deduplicate by stable order and session identifiers.
- Cart abandonment is measured only for eligible cart sessions whose recorded session end has been idle for at least the 30-minute timeout as of the report's event-time as-of. The numerator is mature cart sessions without a paid conversion; the denominator is all mature eligible cart sessions. Recent carts not past timeout are excluded rather than prematurely labeled abandoned.
- Support contact rate uses distinct filtered sessions with at least one associated support ticket divided by filtered sessions. Support events and tickets are emitted together; a zero result in a filtered cohort is a valid empty state.

## Anomalies, ground truth, and validation

The generator retains source records and emits expected anomaly labels separately in `ground_truth.csv`. The detector does not consume those labels. It detects out-of-order arrival, consent-invalid identity stitching, repeated conversions for the same order, and bot-signaled sessions. Detection is evaluated against ground truth with true/false positives, false negatives, precision, recall, and F1. Baseline bot-signaled sessions are also labeled so the score reflects the complete generated truth set.

Structural checks (primary-key uniqueness, foreign keys, enum domains, event/ingestion time validity, effective assignment dates, and cart/order total reconciliation) are reported separately from intentional anomaly metrics. An injected consent exception is expected to be detected but does not by itself fail parent-key integrity.

## Database schema application

The SQL schema targets PostgreSQL 15+. Apply `schema.sql` to a fresh database and then run `verify_schema.sql`; instructions and expected objects are in [`docs/phase1_verification.md`](docs/phase1_verification.md). When using `--database-url`, the generator appends to the existing schema tables and refuses to load when required tables are missing; it does not replace tables or silently discard schema constraints. The supported production database path is PostgreSQL with the schema applied first.

## Known verification limits

The current available environment for this audit has no Python/test execution capability. The source and test suite have been updated, but no Python tests, generator runs, checksum comparison, PostgreSQL schema execution, or full-scale performance test can be claimed as executed here. Full generation currently stores the generated rows in memory before writing CSVs, so chunked CSV generation remains incomplete and the full-scale resource profile is unverified. See the completion report for tested results and remaining gaps.

The in-browser JourneyIQ Preview is a separate 100-session DEMO DATA presentation; it is not a substitute for the canonical Python-generated CSV dataset or for its scale verification.

## PostgreSQL schema verification

Create a new database named `journeyiq`, connect to it, and execute `schema.sql`, followed by `verify_schema.sql`. The verification script checks the ten entities, bridge tables, keys, indexes, and audit views. The documented relationship model keeps foreign-key deletion behavior restrictive so historical source records remain traceable.
