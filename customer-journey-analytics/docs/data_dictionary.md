# JourneyIQ data dictionary

PostgreSQL 15+ is the production target. Names below match the canonical SQL tables and CSV export names. All timestamps are UTC `TIMESTAMPTZ`; identifier values are application-assigned, immutable strings. `PK`, `FK`, and `UQ` denote primary, foreign, and unique keys. `NOT NULL` means required. A nullable FK is intentionally absent when identity or linkage is unavailable. Check constraints in `schema.sql` are authoritative for enumerations and numeric limits.

## 1. Customer — `customers`
One row per known customer identity. Anonymous visitors do not receive a customer record until a legitimate identity is available.

| Column | PostgreSQL type | Required | Key / allowed values | Meaning |
|---|---|---:|---|---|
| `customer_id` | `VARCHAR(16)` | Yes | PK; `CUS-` plus six digits | Immutable customer identifier, e.g. `CUS-000001`. |
| `created_at` | `TIMESTAMPTZ` | Yes | | First-known customer creation time. |
| `consent_status` | `VARCHAR(12)` | Yes | `granted`, `denied`, `unknown` | Current consent state recorded for the profile. Identity use remains purpose/consent dependent. |
| `lifecycle_state` | `VARCHAR(16)` | Yes | `active`, `inactive`, `deleted` | Current profile lifecycle state. |
| `country` | `CHAR(2)` | No | ISO 3166-1 alpha-2 | Country code; nullable when unknown. |

Cardinality: customer `1 → 0..N` sessions, events, carts, orders, and support tickets. Consent changes should be recorded in a production consent-history extension; this base profile describes current state, not a full consent audit log.

## 2. Session — `sessions`
One source session with a stable session key and attribution context. Raw event streams should be sessionized using a 30-minute inactivity timeout; this table stores the resulting session boundary.

| Column | PostgreSQL type | Required | Key / allowed values | Meaning |
|---|---|---:|---|---|
| `session_id` | `VARCHAR(20)` | Yes | PK; `SES-YYYY-` plus six digits | Deterministic ID, e.g. `SES-2026-000001`. |
| `customer_id` | `VARCHAR(16)` | No | FK → `customers.customer_id` | Consent-authorized linked customer, otherwise NULL. |
| `anonymous_id` | `VARCHAR(24)` | Yes | | Pseudonymous browser/app identity used when no legitimate customer link is present. |
| `started_at` | `TIMESTAMPTZ` | Yes | | First event occurrence/session start. |
| `ended_at` | `TIMESTAMPTZ` | No | `>= started_at` | Last event/session end; NULL for open sessions. |
| `channel` | `VARCHAR(16)` | Yes | `website`, `mobile_app` | Originating channel. |
| `device_type` | `VARCHAR(16)` | Yes | `desktop`, `mobile`, `tablet` | Device class. |
| `consent_status` | `VARCHAR(12)` | Yes | `granted`, `denied`, `unknown` | Consent applicable to this session. |
| `is_bot` | `BOOLEAN` | Yes | defaults `FALSE` | Session-level bot classification; detailed evidence belongs in event properties. |
| `lifecycle_state` | `VARCHAR(16)` | Yes | `active`, `completed`, `expired` | Session lifecycle. |

Cardinality: session `1 → 0..N` events, carts, orders, support tickets, experiment assignments; session `1 → 0..1` outcome. The base schema allows NULL customer linkage. Consent compliance and linkage correctness are validation rules because injected identity-stitching exceptions must remain storable and auditable.

## 3. JourneyEvent — `journey_events`
Append-only event history; retain event occurrence and original ingestion timestamps independently. Duplicate-source records remain present; analytical conversion metrics deduplicate by session/order identity rather than deleting evidence.

| Column | PostgreSQL type | Required | Key / allowed values | Meaning |
|---|---|---:|---|---|
| `event_id` | `VARCHAR(64)` | Yes | PK; `EVT-<session_id>-<six-digit sequence>` | Immutable session-scoped event ID. |
| `session_id` | `VARCHAR(20)` | Yes | FK → sessions | Session owning the event. |
| `customer_id` | `VARCHAR(16)` | No | FK → customers | Legitimately resolved customer at event time; NULL for anonymous/unlinked activity. |
| `anonymous_id` | `VARCHAR(24)` | Yes | | Anonymous identity observed by source. |
| `event_type` | `VARCHAR(40)` | Yes | `session_started`, `page_viewed`, `product_viewed`, `added_to_cart`, `checkout_started`, `payment_attempted`, `purchase_completed`, `purchase_failed`, `support_contacted` | Versioned event taxonomy. |
| `event_timestamp` | `TIMESTAMPTZ` | Yes | | When the action occurred. |
| `ingestion_timestamp` | `TIMESTAMPTZ` | Yes | `>= event_timestamp` for this data contract | When the platform received the event; preserves event latency and arrival ordering. |
| `channel` | `VARCHAR(16)` | Yes | `website`, `mobile_app` | Event source channel. |
| `page_id` | `VARCHAR(16)` | No | FK → pages | Page involved where applicable. |
| `product_id` | `VARCHAR(16)` | No | FK → products | Product involved where applicable. |
| `event_properties` | `JSONB` | Yes | defaults `{}` | Typed-by-version source properties; purchase events carry the stable `order_id` here for idempotent duplicate-conversion detection. Never place ground-truth labels here. |
| `event_version` | `VARCHAR(12)` | Yes | non-empty schema version, e.g. `1.0` | Event payload contract version. |

Expected taxonomy attributes: `session_started` has no required page/product; `page_viewed` and `product_viewed` use `page_id`; `product_viewed`, `added_to_cart`, and `purchase_completed` use `product_id`; checkout/payment/support events may carry relevant page or case properties. Session `1 → N` events; page/product `1 → 0..N` events.

## 4. Page — `pages`
Versionable catalog of experience locations used for page-level friction analysis.

| Column | PostgreSQL type | Required | Key / allowed values | Meaning |
|---|---|---:|---|---|
| `page_id` | `VARCHAR(16)` | Yes | PK; `PAG-` plus six digits | Stable page key. |
| `page_name` | `TEXT` | Yes | | Human-readable name. |
| `page_type` | `VARCHAR(24)` | Yes | `landing`, `discovery`, `product`, `cart`, `checkout`, `payment`, `support`, `campaign` | Page classification. |
| `is_active` | `BOOLEAN` | Yes | defaults `TRUE` | Whether the page is currently active. |
| `effective_from` | `TIMESTAMPTZ` | Yes | | Beginning of the page catalog version's validity. |
| `effective_to` | `TIMESTAMPTZ` | No | `>= effective_from` | Exclusive catalog end is not used in the starter; NULL means no scheduled end. |

Cardinality: page `1 → 0..N` journey events. Inactive pages remain for historical references; events should fall in the referenced page version's effective interval.

## 5. Product — `products`
Product catalog snapshot used to contextualize views, cart line items, and orders.

| Column | PostgreSQL type | Required | Key / allowed values | Meaning |
|---|---|---:|---|---|
| `product_id` | `VARCHAR(16)` | Yes | PK; `PRD-` plus six digits | Stable product key. |
| `product_name` | `TEXT` | Yes | | Display name. |
| `category` | `TEXT` | Yes | | Product category. |
| `unit_price` | `NUMERIC(12,2)` | Yes | `>= 0` | Current catalog unit price in the product's configured currency (starter data uses USD). |
| `is_active` | `BOOLEAN` | Yes | defaults `TRUE` | Product availability state. |
| `effective_from` | `TIMESTAMPTZ` | Yes | | Beginning of this product catalog version's validity. |
| `effective_to` | `TIMESTAMPTZ` | No | `>= effective_from` | NULL means no scheduled end; price snapshots remain on cart items. |

Cardinality: product `1 → 0..N` events and cart items. Product/page changes are represented as effective-dated versions; cart-item unit price snapshots preserve the price at cart time.

## 6. Cart — `carts`
A session's cart lifecycle record.

| Column | PostgreSQL type | Required | Key / allowed values | Meaning |
|---|---|---:|---|---|
| `cart_id` | `VARCHAR(20)` | Yes | PK; `CRT-` plus six digits | Stable cart key. |
| `session_id` | `VARCHAR(20)` | Yes | FK → sessions | Session that created the cart. |
| `customer_id` | `VARCHAR(16)` | No | FK → customers | Consent-authorized identity, if known. |
| `created_at` | `TIMESTAMPTZ` | Yes | | Cart creation time. |
| `state` | `VARCHAR(16)` | Yes | `open`, `abandoned`, `converted`, `expired` | Current lifecycle state. |

Cardinality: session `1 → 0..N` carts; cart `1 → 1..N` cart items; cart `0..1 → N` orders only where repeat/partial orders are permitted (starter rules use at most one conversion per cart).

## 7. Order — `orders`
Purchase/checkout transaction source record. Order IDs are the preferred idempotency key for conversion counting.

| Column | PostgreSQL type | Required | Key / allowed values | Meaning |
|---|---|---:|---|---|
| `order_id` | `VARCHAR(20)` | Yes | PK; `ORD-` plus six digits | Immutable order key. |
| `session_id` | `VARCHAR(20)` | Yes | FK → sessions | Converting session. |
| `customer_id` | `VARCHAR(16)` | No | FK → customers | Consent-authorized customer at order time. |
| `cart_id` | `VARCHAR(20)` | No | FK → carts | Originating cart where one exists. |
| `ordered_at` | `TIMESTAMPTZ` | Yes | | Order creation/attempt time. |
| `status` | `VARCHAR(16)` | Yes | `pending`, `paid`, `failed`, `refunded` | Order lifecycle/financial status. |
| `total_amount` | `NUMERIC(12,2)` | Yes | `>= 0` | Order grand total. |
| `currency` | `CHAR(3)` | Yes | ISO 4217, uppercase | Currency of order total. |

Cardinality: session `1 → 0..N` orders; optional cart `1 → 0..N` orders; customer `1 → 0..N` orders. Cart/order amount reconciliation is a reporting validation (tax, shipping, discount treatment must be explicit); it cannot be expressed by a row-local `CHECK` constraint.

## 8. SupportTicket — `support_tickets`
Support contact linked to the originating journey when available.

| Column | PostgreSQL type | Required | Key / allowed values | Meaning |
|---|---|---:|---|---|
| `ticket_id` | `VARCHAR(20)` | Yes | PK; `SUP-` plus six digits | Stable support case key. |
| `session_id` | `VARCHAR(20)` | Yes | FK → sessions | Session associated with contact. |
| `customer_id` | `VARCHAR(16)` | No | FK → customers | Consent-authorized known customer. |
| `created_at` | `TIMESTAMPTZ` | Yes | | Ticket creation time. |
| `status` | `VARCHAR(16)` | Yes | `open`, `pending`, `resolved`, `closed` | Ticket lifecycle state. |
| `reason` | `TEXT` | Yes | | Normalized reason or original category. |

Cardinality: session `1 → 0..N` tickets; customer `1 → 0..N` tickets.

## 9. Experiment — `experiments`
Experiment definition and effective interval.

| Column | PostgreSQL type | Required | Key / allowed values | Meaning |
|---|---|---:|---|---|
| `experiment_id` | `VARCHAR(16)` | Yes | PK; `EXP-YYYY-` plus six digits | Stable experiment ID. |
| `name` | `TEXT` | Yes | | Experiment name. |
| `status` | `VARCHAR(16)` | Yes | `draft`, `active`, `completed`, `paused` | Experiment lifecycle state. |
| `start_at` | `TIMESTAMPTZ` | Yes | | Effective start instant. |
| `end_at` | `TIMESTAMPTZ` | Yes | `>= start_at` | Effective end instant. |

Cardinality: experiment `1 → 0..N` assignments. Variants are stored on assignments, enabling controlled experiment-specific values without an enum migration.

## 10. JourneyOutcome — `journey_outcomes`
One derived, reproducible classification per session under a named rule version. This is not an independently randomized label.

| Column | PostgreSQL type | Required | Key / allowed values | Meaning |
|---|---|---:|---|---|
| `outcome_id` | `VARCHAR(32)` | Yes | PK; `OUT-SES-YYYY-NNNNNN` | Deterministic outcome identifier. |
| `session_id` | `VARCHAR(20)` | Yes | FK + UQ → sessions | The session classified; one current outcome per session. |
| `outcome_type` | `VARCHAR(32)` | Yes | `converted`, `checkout_abandoned`, `cart_abandoned`, `browsed`, `bot` | Classification derived from source signals. |
| `outcome_at` | `TIMESTAMPTZ` | Yes | | Evaluation/as-of instant. |
| `rule_version` | `VARCHAR(12)` | Yes | non-empty, e.g. `1.0` | Version of classification logic. |

Priority used by the starter rule: bot → converted (successful purchase event/order) → checkout abandoned (checkout without success) → cart abandoned (cart without checkout) → browsed. Cardinality session `1 → 0..1` outcome. Store prior rule versions in a history table if multiple historical classifications per session are required.

## Bridge tables

### CartItem — `cart_items`
Cart-to-product many-to-many bridge with quantity and cart-time price. `cart_item_id VARCHAR(20)` is PK (`CIT-` plus six digits); `cart_id VARCHAR(20)` is required FK to carts; `product_id VARCHAR(16)` is required FK to products; `quantity INTEGER NOT NULL CHECK (quantity > 0)`; `unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0)`; `UNIQUE(cart_id, product_id)` prevents duplicate lines for a product in one cart. Cardinality cart `1 → 1..N` items and product `1 → 0..N` items.

### ExperimentAssignment — `experiment_assignments`
Experiment-to-session many-to-many bridge with assigned variant and time. `assignment_id VARCHAR(20)` is PK (`ASN-` plus six digits); `experiment_id VARCHAR(16)` required FK to experiments; `session_id VARCHAR(20)` required FK to sessions; `variant VARCHAR(32)` required non-empty label; `assigned_at TIMESTAMPTZ` required; `UNIQUE(experiment_id, session_id)` allows one assignment per session per experiment. Cardinality experiment `1 → 0..N` assignments and session `1 → 0..N` assignments.

## Database constraints versus analytic validation

PK/FK/unique checks, enum domains, nonnegative money/quantity, and row-local timestamp checks are enforced in `schema.sql`. Consent-aware stitching, event-to-session identity consistency, lifecycle transition histories, duplicate semantic conversions, cart/order totals, event arrival order, 30-minute sessionization, funnel monotonicity, and outcome/source consistency require cross-row or historical knowledge; validate them in the pipeline report rather than using unsafe row-local constraints. The deliberate anomaly fixture is retained for these exception tests. The SQL schema intentionally allows raw anomalous identity evidence to be inserted so it can be detected rather than discarded.
