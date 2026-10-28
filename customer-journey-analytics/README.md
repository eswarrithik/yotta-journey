# YottaJourney · Customer Journey Analytics

A reproducible Python data pipeline and Streamlit analytics workspace for YottaFlex.ai. The generator runs independently from the dashboard and exports deterministic CSV datasets, validation results, and SHA-256 manifests. PostgreSQL DDL is provided for production; SQLAlchemy supports PostgreSQL URLs and SQLite URLs for local evaluation.

## Start here

Install `requirements.txt`, then run the module with `PYTHONPATH=src python -m yottajourney.pipeline --output data`. The default seed is `20261022`; defaults produce 100 sessions and roughly 2,000 events. Full generation: add `--full` (100,000 sessions). Optional SQLAlchemy persistence accepts `--database-url` or `DATABASE_URL`, for example `sqlite:///journey.db` or a PostgreSQL SQLAlchemy URL. Launch the dashboard separately with `streamlit run app.py`. Run automated checks with `pytest`.

Exports include one CSV per relational table, `ground_truth.csv` (evaluation-only anomaly labels), `validation_report.json`, and `reproducibility.json`. Checksums intentionally cover input-entity CSVs, not runtime metadata or the ground-truth labels. The same seed/configuration yields stable sorted rows and serialization.

## Entity model

`customers` 1—many `sessions`; session 1—many `journey_events`, carts, orders, support tickets, and events; cart 1—many cart items; product 1—many cart items/events; experiment 1—many assignments, with one assignment per experiment/session; session 1—one derived journey outcome. Events and session/order links preserve both anonymous and consent-authorized customer identifiers. The PostgreSQL schema in `schema.sql` includes PK, FK, unique, check, lifecycle, and timestamp constraints. The generator's anomaly cases deliberately violate only the described analytical conditions, not parent key integrity.

## Event taxonomy and measurement rules

Event names: `session_started`, `page_viewed`, `product_viewed`, `added_to_cart`, `checkout_started`, `payment_attempted`, `purchase_completed`, `purchase_failed`, and `support_contacted`. Channel is website/mobile_app; event time is occurrence time and ingestion time is arrival time; properties carry the schema version, device, and bot signal. A session is a source session record; the prescribed inactivity boundary is 30 minutes for sessionization of raw event streams. IDs are immutable and deterministic (CUS, SES, session-scoped EVT, EXP, OUT). Consent denied/unknown sessions do not carry linked customer IDs.

Funnel order is Session Started → Product Viewed → Added to Cart → Checkout Started → Purchase Completed. Stage counts are distinct eligible sessions with at least one stage event, filtered by channel/device. Each stage conversion divides by the immediately preceding stage count; first stage is 100%. Overall purchase conversion divides distinct purchase sessions by filtered session count. A session contributes at most one conversion; cart abandonment is carts without a purchase divided by carts. Support contact rate is sessions with ≥1 ticket divided by eligible sessions. Event latency is ingestion minus occurrence; page friction ranks events by observed median ingestion latency and volume. Outcomes derive from observed purchase, checkout, cart, and bot signals in that priority sequence rather than independent labels.

## Anomalies and quality

After a baseline is generated, the starter dataset injects four traceable examples: out-of-order arrivals with nonnegative per-event latency, unauthorized identity linkage on a denied-consent session, a duplicate purchase event, and bot-signaled activity. The detector consumes only source event/session fields; ground truth is loaded only for precision/recall/F1 evaluation. Validation reports include per-table row counts, PK/FK checks, funnel counts, purchase reconciliation, and exception notes. Database uniqueness is enforced at insertion when using the production schema; raw source event rows are preserved in CSV output.

## Scale note

The `--full` profile switches the same seeded generation rules to 100,000 sessions / approximately 2,000,000 events. Database writes use bounded SQLAlchemy batches; tune `chunk_size` for the host. CSV tables are generated separately and remain the canonical export boundary.
