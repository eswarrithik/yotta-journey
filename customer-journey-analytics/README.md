# JourneyIQ Customer Journey Analytics

JourneyIQ combines a deterministic synthetic-data pipeline, PostgreSQL schema, validation/reproducibility reports, automated tests, and Streamlit dashboards. The existing React preview remains a separate 100-session DEMO DATA sample; it is not a substitute for the Python generator or full-scale verification.

## Windows setup (PowerShell)

Run from the repository root. Python 3.11 is recommended.

```powershell
cd customer-journey-analytics
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
$env:PYTHONPATH = (Join-Path (Get-Location) "src")
```

The optional PostgreSQL connection setting is shown blank in `.env.example`. CSV-only use does not require a database connection. Never commit a populated `.env`, password, API key, or database credential.

## Generate data

Starter profile (seed `20261022`, 100 sessions, exactly 20 event rows per session / 2,000 events):

```powershell
python -m yottajourney.pipeline --output data --seed 20261022
```

**Separate full-dataset generation command** (100,000 sessions; 2,000,000 events, exactly 20 per session):

```powershell
python -m yottajourney.pipeline --full --output data-full --seed 20261022
```

A custom profile can use `--sessions`, `--customers`, `--chunk-size`, and `--start-date`:

```powershell
python -m yottajourney.pipeline --sessions 250 --customers 180 --chunk-size 5000 --start-date 2026-01-01 --output data-custom --seed 20261022
```

The CLI writes the deterministic event CSV in chunks and does not retain the 2-million-row canonical event DataFrame. It also reads event chunks for analytics, anomaly detection, structural checks, PostgreSQL inserts, and filtered dashboard exports. Exact latency medians retain compact numeric arrays, so metric state still scales with latency observations; full event records are not retained. The Python API keeps `retain_tables=True` by default for small-data compatibility; CLI generation and paired reproducibility use `retain_tables=False`.

An injected duplicate conversion replaces a padded page-view slot; it does not add a 21st row to the session. Ground-truth labels remain isolated in `ground_truth.csv`, separate from detector inputs. Output includes entity CSVs, the standalone ground-truth CSV, `validation_report.json`, and `reproducibility.json` with row counts and SHA-256 fingerprints.

## Verification workflow (PowerShell)

Run the test suite and starter checks from the project folder:

```powershell
python -m pytest tests/test_pipeline.py -q
python -m pytest tests/test_demo_dashboard_data.py -q
python -m pytest -q
python -m yottajourney.pipeline --output data-starter --seed 20261022
```

Check the actual generated counts, every entity validation result, anomaly metrics, and SHA-256 fingerprints from the artifacts (this fails if the dataset target or any structural check fails):

```powershell
@'
import hashlib, json
from pathlib import Path
def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
p = Path("data-starter")
report = json.loads((p / "validation_report.json").read_text())
manifest = json.loads((p / "reproducibility.json").read_text())
assert report["status"] == "passed", report["errors"]
assert report["entity_row_counts"]["sessions"] == 100
assert report["entity_row_counts"]["journey_events"] == 2_000
assert report["checks"]["event_volume_target"]
assert report["checks"]["events_per_session_target"]
assert all(report["checks"].values()), report["errors"]
assert report["anomaly_evaluation"]["false_positives"] == 0
assert report["anomaly_evaluation"]["false_negatives"] == 0
for name, expected in manifest["sha256"].items():
    actual = sha256(p / name)
    assert actual == expected, name
print(json.dumps({"status": "PASS", "entity_row_counts": report["entity_row_counts"], "anomaly_evaluation": report["anomaly_evaluation"], "sha256_files_verified": len(manifest["sha256"])}, indent=2))
'@ | python -
```

Run paired starter reproducibility (two independent runs; the comparison is written to the manifest):

```powershell
python -m yottajourney.pipeline --output data-repro --seed 20261022 --verify-reproducibility
```

Use the same artifact check above with `data-repro`, and confirm `reproducibility.json` has `comparison.identical: true`. The paired run compares every canonical CSV SHA-256, row counts, derived metrics, and anomaly counts.

For the **full-scale run**, use the separate command above, then check actual outputs (do not infer success from `Config.full()`):

```powershell
@'
import hashlib, json
from pathlib import Path
def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
p = Path("data-full")
report = json.loads((p / "validation_report.json").read_text())
manifest = json.loads((p / "reproducibility.json").read_text())
assert report["status"] == "passed", report["errors"]
assert report["entity_row_counts"]["sessions"] == 100_000
assert report["entity_row_counts"]["journey_events"] == 2_000_000
assert report["checks"]["event_volume_target"]
assert report["checks"]["events_per_session_target"]
assert all(report["checks"].values()), report["errors"]
for name, expected in manifest["sha256"].items():
    assert sha256(p / name) == expected, name
print(json.dumps({"status": "PASS", "entity_row_counts": report["entity_row_counts"], "sha256_files_verified": len(manifest["sha256"])}, indent=2))
'@ | python -
```

The full command generates one dataset, not a second paired full-scale dataset. Run `--verify-reproducibility` separately only when there is sufficient disk and runtime capacity.

## Launch dashboards

Standalone deterministic 100-session DEMO DATA dashboard:

```powershell
python -m streamlit run dashboard/app.py
```

Pipeline-backed dashboard (generate `data/` first):

```powershell
python -m streamlit run app.py
```

The pipeline-backed dashboard reads the event CSV in chunks for analytics, anomaly detection, counts, and CSV/JSON exports. It reports generated and filtered counts separately; the standalone dashboard remains an independent synthetic preview.

## Database schema (optional)

The production schema targets PostgreSQL 15+. Create a `journeyiq` database, then apply `schema.sql` and `verify_schema.sql` with your PostgreSQL client. The generator accepts `--database-url` or `DATABASE_URL` and appends to an already-created schema; it does not create or replace tables. `analytics.sql` provides funnel, conversion, mature-cart abandonment, duplicate-conversion, identity-exception, and arrival-order queries.

## Entity and business contracts

The ten required entities are Customer, Session, JourneyEvent, Page, Product, Cart, Order, SupportTicket, Experiment, and JourneyOutcome. CartItem and ExperimentAssignment are relationship tables. See:

- [`docs/data_dictionary.md`](docs/data_dictionary.md) — field contracts and keys.
- [`docs/relationships.md`](docs/relationships.md) — cardinalities, referential behavior, and ER model.
- [`docs/business_rules.md`](docs/business_rules.md) — consent, session timeout, funnel eligibility, conversion, abandonment, and anomaly policy.
- [`docs/synthetic_data_manifest.md`](docs/synthetic_data_manifest.md) — synthetic source and generation contract.
- [`docs/verification_report.md`](docs/verification_report.md) — honest PASS / FAIL / BLOCKED verification status and exact local commands.

Business measures use distinct eligible human funnel-entry sessions; purchase events are not raw conversion counts. Cart abandonment excludes carts that have not been idle for the documented 30-minute timeout. Injected anomalies are evaluated separately from structural integrity.

## Current verification limitation

The current agent environment has no Python interpreter, pytest runner, PostgreSQL server, or Streamlit launch facility exposed to it. Python runtime checks and dataset execution therefore remain BLOCKED here; no generator counts or checksums are claimed as verified. The exact local commands above are provided to complete and record those checks. See `docs/verification_report.md`.
