# YottaJourney relationship model

`schema.sql` is the executable PostgreSQL DDL. `data_dictionary.md` is the field-level contract. All relationships are physical foreign keys except the consent/identity validity rule, which is a cross-record analytics validation so source anomalies remain detectable.

## Relationship inventory

| Parent | Child | Cardinality | Constraint / behavior |
|---|---|---|---|
| `customers` | `sessions` | 1 : 0..N | `sessions.customer_id` nullable FK; NULL when not identified or not linkable. |
| `customers` | `journey_events` | 1 : 0..N | `journey_events.customer_id` nullable FK, identity at event time. |
| `customers` | `carts` | 1 : 0..N | Nullable FK. |
| `customers` | `orders` | 1 : 0..N | Nullable FK. |
| `customers` | `support_tickets` | 1 : 0..N | Nullable FK. |
| `sessions` | `journey_events` | 1 : 0..N | Required FK; append-only event history, indexed by `(session_id, event_timestamp)`. |
| `sessions` | `carts` | 1 : 0..N | Required FK; multiple carts allowed over a session lifecycle. |
| `sessions` | `orders` | 1 : 0..N | Required FK; may include multiple attempts/orders. Idempotent conversion analytics count distinct order/session IDs per stated metric. |
| `sessions` | `support_tickets` | 1 : 0..N | Required FK. |
| `sessions` | `experiment_assignments` | 1 : 0..N | Required FK; one assignment per experiment/session pair. |
| `sessions` | `journey_outcomes` | 1 : 0..1 | Required FK and unique constraint on outcome `session_id`; one current classification per session. |
| `pages` | `journey_events` | 1 : 0..N | Nullable event FK (not every event is a page event). Restrict deletion of referenced page. |
| `products` | `journey_events` | 1 : 0..N | Nullable event FK. |
| `products` | `cart_items` | 1 : 0..N | Required FK on bridge row. |
| `carts` | `cart_items` | 1 : 1..N | Required FK; unique `(cart_id, product_id)` means one line per product in a cart. |
| `carts` | `orders` | 1 : 0..N | Nullable order FK; multiple order attempts are retained. |
| `experiments` | `experiment_assignments` | 1 : 0..N | Required FK; assignment effective time must fall in the experiment interval (cross-row validation). |

## ER overview

```text
Customer 1 ─────< Session 1 ─────< JourneyEvent >───── 0..1 Page
    │                  │                  └──────────── 0..1 Product
    │                  ├─────< Cart 1 ─────< CartItem >───── 1 Product
    │                  │          └─────< Order
    │                  ├─────< Order
    │                  ├─────< SupportTicket
    │                  ├─────< ExperimentAssignment >───── 1 Experiment
    │                  └───── 0..1 JourneyOutcome
    ├─────< JourneyEvent (optional identity at event time)
    ├─────< Cart (optional identity)
    ├─────< Order (optional identity)
    └─────< SupportTicket (optional identity)
```

## Delete/update and lifecycle semantics

All IDs are immutable application identifiers and primary keys. Foreign keys use PostgreSQL's default `NO ACTION`: a parent cannot be removed while historical child records reference it. Use `is_active`/lifecycle state for catalog/profile deactivation, not physical deletion. Source journey events are append-only; correcting event data should be represented by a new correction/version record in a future event-revision extension, not in-place deletion. Cart/order status values describe lifecycle state; enforcing allowed transition sequences requires transition history and is covered by data-quality rules, not a single-row check.

## Key business validations not reducible to FK constraints

- Session and event `customer_id` must not be linked if the applicable session consent is denied or unknown.
- When both are populated, event customer identity should agree with the session's eligible linked identity; exceptions are retained and surfaced by the identity detector.
- Event occurrence ordering and ingestion ordering are distinct; ingestion time must not precede occurrence under the current source contract, but events may arrive out of occurrence order relative to other events.
- One semantic conversion is counted per order ID (or session for the session-conversion funnel); raw duplicate event rows remain queryable.
- Cart totals and order totals are reconciled by analytics. Tax, discounts, shipping, and currency conversions must be included consistently before exact total equality is asserted.
- Experiment assignment timestamp must be inside the experiment's effective interval.
- Outcomes must agree with source events using the recorded `rule_version`.

## Index strategy

The schema provides PK/unique indexes automatically, plus indexes on event session-time, event ingestion-time, event type-time, customer-time, session channel/device/time, all high-use FK joins, order time/status, cart state/time, ticket time/status, experiment effective dates, assignments by session/time, and outcome type/time. Event query patterns favor `(session_id, event_timestamp)` for ordered journey reconstruction and BRIN on ingestion time for large append-heavy partitions. Indexes are deliberately non-unique unless a uniqueness rule is a business invariant.
