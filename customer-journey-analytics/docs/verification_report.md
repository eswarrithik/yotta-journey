# JourneyIQ verification report

**Report date:** 2026-10-29  
**Verification scope:** JourneyIQ Python generator, streamed analytics, CSV exports, tests, reproducibility, optional PostgreSQL, and Streamlit.  
**Overall:** implementation work is present, but runtime verification is **BLOCKED** because this agent environment exposes no Python interpreter/pytest execution facility. No generator run, dataset count, or file checksum is claimed as verified.

## Status summary

| Status | Result |
|---|---|
| PASS — static implementation review | CLI generation and paired reproducibility request `retain_tables=False`; event CSV writes use a bounded buffer; stream-based analysis, anomaly detection, event validation, database inserts, and dashboard exports process event chunks. The generator reuses a padded event slot for duplicate-conversion evidence so the intended event volume remains 20 per session. Exact latency medians retain compact numeric arrays, so metric state still scales with latency observations even though full event records are not retained. |
| PASS — workspace TypeScript diagnostic | The available workspace type check completed with “No type errors found.” This check covers the separate React/Vite workspace, not the JourneyIQ Python code. |
| PASS — test coverage added | Tests now cover small-fixture streamed-vs-in-memory analytics, streamed anomaly parity, CSV/JSON export row counts, and no-event-DataFrame report generation. **These are test cases, not executed test results.** |
| FAIL | No executed check has produced a known failure in this turn. This is not evidence that the Python code passes; Python execution was unavailable. |
| BLOCKED — Python tests/runtime | Python, pytest, the generator, and Streamlit could not be executed from the current agent environment. |
| BLOCKED — starter dataset | Actual entity counts, exact per-session 20-event counts, all primary/foreign keys, lifecycle/time checks, anomaly scores, ground-truth separation, funnel results, and checksums have not been generated or inspected at runtime. |
| BLOCKED — streaming parity and exports | The parity, anomaly, and export tests are present but were not run. No filtered CSV/JSON output has been generated or compared. |
| BLOCKED — reproducibility | No paired run or SHA-256 comparisons were executed. |
| BLOCKED — database and dashboard | No PostgreSQL service was available for integration; no Python/Streamlit launch was performed. |
| BLOCKED — full scale | The 100,000-session / 2,000,000-event profile has **not** been generated. No full-scale count, performance, memory, or checksum success is claimed. |

## Environment inspection and checks run

- Inspected the JourneyIQ source, tests, README, requirements, data manifest, and prior verification notes.
- Queried available server logs for Python; no matching Python execution logs were present.
- The project declares pytest and pandas dependencies, and provides Windows setup/run instructions, but those declarations do not establish that dependencies are installed in this agent environment.
- The available workspace TypeScript check was run and returned **“No type errors found.”** It does not import or validate the Python subsystem. No production build was run because this Vite build would not execute the Python generator or Streamlit application.
- No shell/terminal command was available to invoke `python`, `pytest`, PostgreSQL, or Streamlit here. No Python test command is listed as executed.
- Static code review was the only check possible for the Python changes. The separate React/Vite preview is not a Python runner and is not evidence about the JourneyIQ Python implementation.

## Exact Windows verification commands

Run from PowerShell at the repository root:

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

Generate the starter profile and its validation/checksum files:

```powershell
python -m yottajourney.pipeline --output data-starter --seed 20261022
```

Verify that the generated report says PASS, contains exactly 100 sessions and 2,000 events, has every structural check true, reports zero anomaly false positives/false negatives, and that each recorded SHA-256 matches the actual file:

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

Run paired starter reproducibility, then check that the paired comparison is true:

```powershell
python -m yottajourney.pipeline --output data-repro --seed 20261022 --verify-reproducibility
python -c "import json,pathlib; m=json.loads(pathlib.Path('data-repro/reproducibility.json').read_text()); assert m['comparison']['identical'], m['comparison']; print(json.dumps(m['comparison'], indent=2))"
```

**Separate full-dataset generation command** (do not use this as evidence before it finishes):

```powershell
python -m yottajourney.pipeline --full --output data-full --seed 20261022
```

After that command completes, independently verify the expected full counts, structural checks, per-session target, and every output checksum:

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

`--verify-reproducibility` intentionally generates a second dataset. A paired full-scale run is optional and will require extra time and disk space. PostgreSQL and Streamlit should be tested separately only in environments with those services available; the commands are documented in `README.md`.

## Changed files in this implementation turn

- `src/yottajourney/streaming.py` — new chunk readers, analytics aggregation, anomaly detection, structural event validation, and filtered export functions.
- `src/yottajourney/pipeline.py` — optional non-retained event table; CLI and reproducibility paths use streamed processing; event IDs/order/counts and validation/checksum reports are retained; inserts are chunked.
- `app.py` — pipeline-backed dashboard no longer loads the canonical event DataFrame; analysis, anomaly results, and exports read/write chunks.
- `tests/test_pipeline.py` — parity and streamed export coverage added; not run in this environment.
- `README.md`, `docs/synthetic_data_manifest.md` — updated operating instructions and memory/count contracts.
- `docs/verification_report.md` — this report.

This report should be updated with the actual command outputs after a Python-capable Windows run. Until then, all runtime results above remain BLOCKED.
