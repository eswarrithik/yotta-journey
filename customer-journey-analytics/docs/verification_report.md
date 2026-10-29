# JourneyIQ final acceptance audit

**Audit date:** 2026-10-29  
**Scope:** the committed JourneyIQ implementation, tests, and report, plus fixes made during this acceptance audit.  
**Overall acceptance:** **BLOCKED**. The source contains the requested generator and verification paths, but Python tests and generated artifacts cannot be executed in this environment. No actual generated row counts, anomaly scores, output checksums, or full-scale success are claimed.

## Acceptance matrix

| # | Requirement | Status | Evidence / limitation |
|---|---|---|---|
| 1 | Starter profile: seed `20261022`, 100 sessions, approximately 2,000 events | **BLOCKED** | `Config()` defaults to seed `20261022` and 100 sessions; generator target is 20 events/session and the test asserts 2,000. The generator was not run, so actual counts are unknown. |
| 2 | Configurable 100,000-session / 2,000,000-event profile | **BLOCKED** | `Config.full()` configures 100,000 sessions and the validator expects 20/session. No full dataset was generated or checked. |
| 3 | Ten required entities, primary keys, foreign keys, relationships | **BLOCKED** | Code contains primary-key, foreign-key, lifecycle, and reconciliation checks; starter tests assert key uniqueness and selected relationships. Runtime validation did not run, so no keys or relationships are marked verified. |
| 4 | Website, mobile app, purchase, support event coverage | **BLOCKED** | Starter tests assert both channels, purchase evidence, and support events/tickets. Tests were not executed. |
| 5 | Four anomalies: out-of-order arrivals, incorrect identity merges, duplicate conversions, bots | **BLOCKED** | Generator labels all four scenarios, and tests compare detections with separate truth. During this audit, duplicate evidence was moved after the original purchase while reusing a padded event slot; a source-reference/time-order assertion was added. Runtime detection remains unverified. |
| 6 | Separate ground truth and precision, recall, F1 | **BLOCKED** | Detection accepts event/session data; truth is evaluated separately via `evaluate_detection`. Tests assert perfect scores and that event properties contain no ground-truth field, but were not run. |
| 7 | CSV and JSON exports contain the correct filtered records | **BLOCKED** | Export tests now compare the entire filtered CSV and JSON payload against the in-memory selected records, not just row totals. Tests were not run and no export was generated. |
| 8 | Generate starter dataset twice; compare stable SHA-256 and row counts | **BLOCKED** | The paired reproducibility path compares CSV hashes, row counts, metrics, and anomaly counts; its test now uses the 100-session starter configuration. No paired generation occurred. |
| 9 | Funnel, abandonment, latency, consent-aware identity, lifecycle rules | **BLOCKED** | Source checks and tests cover these rules, including streamed/in-memory funnel and latency parity. No runtime results exist. |
| 10 | Run every test supported by this environment | **BLOCKED** for JourneyIQ Python tests; **PASS** for the separate workspace TypeScript check | The available TypeScript check returned “No type errors found,” but it does not cover Python. No Python/pytest command can be invoked through the available environment. |

**FAIL:** No test or execution produced a known failure. Because Python execution was unavailable, absence of a reported failure is not a passing result.

## Environment investigation and actual results

- Inspected the committed generator, streaming module, analytics, tests, README, schema, and this report.
- The runtime logs contain React/Vite browser activity; they contain no Python, pytest, generator, PostgreSQL, or Streamlit execution output.
- The project lists `pytest`, `pandas`, and related dependencies, but that does not demonstrate that Python is installed or executable here.
- The available workspace TypeScript check was run and returned **“No type errors found.”** No production build was run; it would not execute JourneyIQ's Python code.
- No Python command was executed. **Actual verified JourneyIQ row counts: none.** Actual generated SHA-256 values: none. Full-scale output: not generated.

## Fixes made during this audit

- Moved the injected duplicate conversion to a sequence position after its source purchase while preserving 20 events/session; added a test for its referenced source event and timestamp order.
- Strengthened filtered-export tests to compare complete CSV and JSON records, not only row counts.
- Changed the paired reproducibility test to use the actual default 100-session starter profile.
- Local checksum-verification snippets hash files incrementally, avoiding reading a multi-million-row CSV into memory.

## Exact Windows PowerShell verification commands

Run from the repository root. Python 3.11 is recommended:

```powershell
cd customer-journey-analytics
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
$env:PYTHONPATH = (Join-Path (Get-Location) "src")
python -m pytest tests/test_pipeline.py -q
python -m pytest tests/test_demo_dashboard_data.py -q
python -m pytest -q
```

Generate and verify a starter dataset twice (the comparison run is included):

```powershell
python -m yottajourney.pipeline --output data-repro --seed 20261022 --verify-reproducibility
```

Then verify generated counts, all structural checks, anomaly scores, and hashes against the actual files. This script hashes in fixed-size blocks:

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
p = Path("data-repro")
report = json.loads((p / "validation_report.json").read_text())
manifest = json.loads((p / "reproducibility.json").read_text())
assert report["status"] == "passed", report["errors"]
assert report["entity_row_counts"]["sessions"] == 100
assert report["entity_row_counts"]["journey_events"] == 2_000
assert report["checks"]["event_volume_target"]
assert report["checks"]["events_per_session_target"]
assert all(report["checks"].values()), report["errors"]
assert manifest["comparison"]["identical"], manifest["comparison"]
assert report["anomaly_evaluation"]["false_positives"] == 0
assert report["anomaly_evaluation"]["false_negatives"] == 0
assert report["anomaly_evaluation"]["precision"] == 1.0
assert report["anomaly_evaluation"]["recall"] == 1.0
assert report["anomaly_evaluation"]["f1"] == 1.0
for name, expected in manifest["sha256"].items():
    assert sha256(p / name) == expected, name
print(json.dumps({"status": "PASS", "entity_row_counts": report["entity_row_counts"], "anomaly_evaluation": report["anomaly_evaluation"], "comparison": manifest["comparison"], "sha256_files_verified": len(manifest["sha256"])}, indent=2))
'@ | python -
```

**Separate full-dataset generation command** (configuration alone is not evidence of success):

```powershell
python -m yottajourney.pipeline --full --output data-full --seed 20261022
```

After it completes, verify actual full counts and every structural check and checksum:

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

These commands have **not** been run in this agent environment. Run `--verify-reproducibility` for the starter profile first; full-scale paired reproducibility would generate another 2-million-event dataset and is intentionally not the default.

## Files changed in this acceptance audit

- `customer-journey-analytics/src/yottajourney/pipeline.py` — preserve chronological source/duplicate-conversion order.
- `customer-journey-analytics/tests/test_pipeline.py` — exact filtered export comparisons, actual starter reproducibility profile, and duplicate source-order assertion.
- `customer-journey-analytics/docs/verification_report.md` — criterion-by-criterion acceptance matrix and commands.

The existing dashboard UI was not redesigned or overwritten. Runtime acceptance remains BLOCKED until the Windows checks above are executed and their outputs are available.
