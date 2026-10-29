# Synthetic data source manifest

| Property | Value |
|---|---|
| Dataset owner | JourneyIQ Customer Journey Analytics project |
| Source class | Programmatically generated synthetic data; no customer or production data is imported |
| Generator | `src/yottajourney/pipeline.py` (`generate`) |
| Seed | `20261022` by default; override with `--seed` |
| Starter profile | 100 sessions, 70 customers, 12 pages, 20 products; code contract targets exactly 2,000 events, including injected duplicate evidence |
| Full profile target | 100,000 sessions and exactly 2,000,000 target events by the 20-events-per-session contract; configured by `Config.full()` but not run/verified in this environment |
| Output | One CSV per entity/bridge table, separate `ground_truth.csv`, plus `validation_report.json` and `reproducibility.json` |
| IDs | Deterministic formatted IDs; event sequence is scoped to a deterministic session ID |
| Serialization | UTF-8 CSV, stable column and row sorting, LF line endings, empty string for missing values |
| Anomaly truth | Kept in `ground_truth.csv`; never passed into `detect_anomalies` |
| Reproducibility | SHA-256 per CSV, row counts, derived metric values, and anomaly counts; paired run via `--verify-reproducibility` |
| PII / credentials | No production PII, passwords, API keys, or database credentials are generated or committed |

## Table outputs

Core entities: `customers.csv`, `sessions.csv`, `journey_events.csv`, `pages.csv`, `products.csv`, `carts.csv`, `orders.csv`, `support_tickets.csv`, `experiments.csv`, and `journey_outcomes.csv`.

Relationship tables: `cart_items.csv` and `experiment_assignments.csv`.

Audit outputs: `ground_truth.csv` contains `entity_id,issue_type`; `validation_report.json` separates structural checks from anomaly evaluation; `reproducibility.json` contains the source profile, hashes, row counts, derived metrics, anomaly counts, and (only after paired verification) the comparison result.

## Generation limitations

`--chunk-size` bounds the event serialization buffer and database insert batches. Event rows are no longer retained as millions of Python dictionaries, but the canonical event DataFrame is loaded for analytics and validation, so end-to-end peak memory is not strictly bounded. The full target profile is configured but not verified; do not treat the profile setting as evidence that 100,000 sessions or 2,000,000 events were generated. See the README for Windows commands and current execution limitations.
