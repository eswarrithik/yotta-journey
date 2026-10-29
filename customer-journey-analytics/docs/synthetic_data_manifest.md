# Synthetic data source manifest

| Property | Value |
|---|---|
| Dataset owner | JourneyIQ Customer Journey Analytics project |
| Source class | Programmatically generated synthetic data; no customer or production data is imported |
| Generator | `src/yottajourney/pipeline.py` (`generate`) |
| Seed | `20261022` by default; override with `--seed` |
| Starter profile | 100 sessions, 70 customers, 12 pages, 20 products; exactly 20 events per session (2,000 total) |
| Full profile target | 100,000 sessions and exactly 2,000,000 events (20 per session); configured by `Config.full()`, not verified at full scale in this environment |
| Output | One CSV per entity/bridge table, separate `ground_truth.csv`, plus validation and reproducibility JSON reports |
| IDs | Deterministic formatted IDs; event sequence is scoped to deterministic session IDs |
| Serialization | UTF-8 CSV, stable event column and row ordering, LF line endings, empty strings for missing values |
| Anomaly truth | Kept in `ground_truth.csv`; never passed to anomaly detectors |
| Reproducibility | SHA-256 per CSV, row counts, derived metric values, and anomaly counts; paired run via `--verify-reproducibility` |
| PII / credentials | No production PII, passwords, API keys, or database credentials are generated or committed |

## Table outputs

Core entities: `customers.csv`, `sessions.csv`, `journey_events.csv`, `pages.csv`, `products.csv`, `carts.csv`, `orders.csv`, `support_tickets.csv`, `experiments.csv`, and `journey_outcomes.csv`.

Relationship tables: `cart_items.csv` and `experiment_assignments.csv`.

Audit outputs: `ground_truth.csv` contains `entity_id,issue_type`; `validation_report.json` separates structural checks from anomaly evaluation; `reproducibility.json` contains the profile, hashes, row counts, derived metrics, anomaly counts, and (only after paired verification) the comparison result.

## Memory and verification limits

The generator CLI writes event CSV chunks and runs analytics, anomaly detection, structural checks, database inserts, and filtered exports from chunks; it does not construct the full canonical event DataFrame. Exact latency medians use compact numeric arrays, so metric state still scales with latency observations. The small-data Python API retains event tables by default for compatibility, and accepts `retain_tables=False` for a streamed result. Chunked analytics are covered by small-fixture parity tests, but those tests have not been run in the current agent environment because Python is not available there.

Full target counts, generated file checksums, paired reproducibility, PostgreSQL integration, and Streamlit runtime remain unverified until run in a Python-capable local environment. The separate full-data command and verification checks are documented in `README.md`; see `docs/verification_report.md` for the current status.

The duplicate-conversion anomaly reuses a padded page-view slot, so it does not create an extra event row and every generated session remains at exactly 20 rows. Ground-truth labels are not embedded in detector inputs.
