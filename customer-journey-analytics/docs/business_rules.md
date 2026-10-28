# JourneyIQ business rules

## Identity, consent, and sessions

- A session is a contiguous journey with a 30-minute inactivity timeout. The synthetic generator emits each session with events less than 30 minutes apart; the last event timestamp is the recorded `ended_at`.
- A customer ID is attached only when the customer consent state is `granted` and the synthetic linking decision succeeds. Denied or unknown consent leaves the session anonymous. The detector flags identity present on a non-granted session or an event/session identity mismatch.
- Raw evidence is preserved. An injected identity exception is intentionally a valid FK to a real customer, but is separately detected and labeled; it is not misreported as a missing-parent failure.

## Event taxonomy and time

- Event names are constrained by `TAXONOMY` in `src/yottajourney/pipeline.py`. Each event has a deterministic, session-scoped event ID, a UTC occurrence timestamp, and an ingestion timestamp.
- Ingestion latency is `ingestion_timestamp - event_timestamp` and must be nonnegative. Out-of-order arrival compares ingestion ordering with occurrence ordering; it does not require negative latency.
- Duplicate conversion rows remain in the raw event data for audit. Detection flags repeated `purchase_completed` events for an order. Funnel and purchase metrics count distinct sessions and paid order IDs so the injected duplicate cannot inflate conversions.

## Funnel and conversion

- Funnel entry eligibility requires at least one `session_started` event and excludes sessions classified as bots.
- Stage reach is the number of distinct eligible sessions with the corresponding event: session start, product view, add to cart, checkout start, purchase complete.
- Stage conversion/drop-off uses the preceding funnel stage as denominator. Overall conversion rate is distinct eligible sessions with a paid order divided by eligible funnel-entry sessions. A raw event count is never the conversion numerator.
- Dashboard filters first select the session cohort by date, channel, device, and product; all funnel stages, orders, support counts, and exports are restricted to that cohort.

## Cart abandonment

- The inactivity timeout is 30 minutes. A cart is eligible for abandonment only when its session's last activity is at least 30 minutes before the report's `as_of` instant.
- Abandoned carts are mature, eligible cart sessions without a paid conversion. The denominator is all mature, eligible cart sessions. Recent carts are excluded until their timeout matures; a missing checkout alone is not sufficient to call an active cart abandoned.

## Support, catalogs, and outcomes

- Support contact rate is distinct filtered sessions with a support ticket divided by filtered sessions. A zero-contact cohort is a valid empty state.
- Page and product catalogs are effective-dated. Each event reference must fall within its referenced catalog row's effective interval.
- Exactly one deterministic `JourneyOutcome` is emitted per session under rule version `1.0`. Priority is bot, converted, checkout abandoned, cart abandoned, then browsed. The value is derived from source events and orders.
- Cart/order reconciliation compares the order amount with cart-item quantity times unit price; the synthetic sample omits tax, discounts, and shipping, so exact equality is expected for carts linked to generated orders.

## Data quality versus anomaly monitoring

- Structural validation checks keys, parent references, enums, timestamps, effective dates, experiment assignment ranges, and cart/order totals.
- Four deliberate anomaly classes are labeled in the separate `ground_truth.csv`: `out_of_order_arrival`, `identity_stitching`, `duplicate_conversion`, and `bot_traffic`. The anomaly detector consumes source events/session fields only; it does not read ground truth. Ground truth is joined only after prediction to calculate precision, recall, and F1.
- The anomaly fixtures are expected detections, not structural integrity failures. Reports display these two quality dimensions separately.
