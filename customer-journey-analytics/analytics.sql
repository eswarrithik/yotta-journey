-- JourneyIQ PostgreSQL analytics examples. Apply schema.sql first.
-- All dashboard filters should be applied to the session cohort before aggregating.

-- Distinct eligible-session funnel and stage-to-stage rates.
WITH eligible_sessions AS (
    SELECT DISTINCT s.session_id
    FROM sessions AS s
    JOIN journey_events AS e ON e.session_id = s.session_id
    WHERE s.is_bot = FALSE
      AND e.event_type = 'session_started'
      -- Add bound parameters for dates/channel/device/product here.
), stages(stage_order, stage_name, event_type) AS (
    VALUES
        (1, 'Session Started', 'session_started'),
        (2, 'Product Viewed', 'product_viewed'),
        (3, 'Added to Cart', 'added_to_cart'),
        (4, 'Checkout Started', 'checkout_started'),
        (5, 'Purchase Completed', 'purchase_completed')
), stage_counts AS (
    SELECT st.stage_order, st.stage_name,
           COUNT(DISTINCT e.session_id) FILTER (WHERE es.session_id IS NOT NULL) AS sessions
    FROM stages AS st
    LEFT JOIN journey_events AS e ON e.event_type = st.event_type
    LEFT JOIN eligible_sessions AS es ON es.session_id = e.session_id
    GROUP BY st.stage_order, st.stage_name
), rates AS (
    SELECT *, LAG(sessions) OVER (ORDER BY stage_order) AS previous_stage_sessions
    FROM stage_counts
)
SELECT stage_name, sessions,
       COALESCE(previous_stage_sessions, (SELECT COUNT(*) FROM eligible_sessions)) AS eligible_sessions,
       sessions::NUMERIC / NULLIF(COALESCE(previous_stage_sessions, (SELECT COUNT(*) FROM eligible_sessions)), 0) AS stage_conversion_rate,
       GREATEST(COALESCE(previous_stage_sessions, (SELECT COUNT(*) FROM eligible_sessions)) - sessions, 0) AS dropoff_sessions
FROM rates
ORDER BY stage_order;

-- Overall conversion uses distinct human eligible sessions and distinct paid-order sessions.
WITH eligible AS (
    SELECT DISTINCT s.session_id
    FROM sessions AS s
    JOIN journey_events AS e ON e.session_id = s.session_id
    WHERE s.is_bot = FALSE AND e.event_type = 'session_started'
), conversions AS (
    SELECT DISTINCT o.session_id
    FROM orders AS o
    JOIN eligible AS e ON e.session_id = o.session_id
    WHERE o.status = 'paid'
)
SELECT COUNT(*) AS eligible_funnel_entries,
       (SELECT COUNT(*) FROM conversions) AS distinct_converting_sessions,
       (SELECT COUNT(*) FROM conversions)::NUMERIC / NULLIF(COUNT(*), 0) AS conversion_rate
FROM eligible;

-- Mature cart abandonment as of a bound report timestamp (:as_of); 30-minute timeout.
WITH eligible AS (
    SELECT DISTINCT s.session_id, COALESCE(s.ended_at, MAX(e.event_timestamp)) AS last_activity
    FROM sessions AS s
    JOIN journey_events AS e ON e.session_id = s.session_id
    WHERE s.is_bot = FALSE
      AND EXISTS (
          SELECT 1 FROM journey_events AS entry
          WHERE entry.session_id = s.session_id AND entry.event_type = 'session_started'
      )
    GROUP BY s.session_id, s.ended_at
), mature_carts AS (
    SELECT DISTINCT c.session_id
    FROM carts AS c
    JOIN eligible AS e ON e.session_id = c.session_id
    WHERE e.last_activity <= :as_of::timestamptz - INTERVAL '30 minutes'
), converted AS (
    SELECT DISTINCT session_id FROM orders WHERE status = 'paid'
)
SELECT COUNT(*) AS eligible_mature_carts,
       COUNT(*) FILTER (WHERE converted.session_id IS NULL) AS abandoned_carts,
       COUNT(*) FILTER (WHERE converted.session_id IS NULL)::NUMERIC / NULLIF(COUNT(*), 0) AS abandonment_rate
FROM mature_carts
LEFT JOIN converted USING (session_id);

-- Duplicate conversion evidence: retain the source rows and expose repeated semantic conversions.
SELECT session_id, event_properties ->> 'order_id' AS order_id,
       COUNT(*) AS conversion_event_rows,
       ARRAY_AGG(event_id ORDER BY event_timestamp, event_id) AS event_ids
FROM journey_events
WHERE event_type = 'purchase_completed'
GROUP BY session_id, event_properties ->> 'order_id'
HAVING COUNT(*) > 1;

-- Consent-invalid identity evidence, including deliberate injected exceptions.
SELECT * FROM session_identity_exceptions ORDER BY session_id, event_id;

-- Out-of-order arrival: event-time and ingestion-time ranks disagree within a session.
WITH ranked AS (
    SELECT session_id, event_id,
           ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY event_timestamp, event_id) AS event_order,
           ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY ingestion_timestamp, event_id) AS arrival_order
    FROM journey_events
)
SELECT session_id, ARRAY_AGG(event_id ORDER BY event_order) AS event_order,
       ARRAY_AGG(event_id ORDER BY arrival_order) AS arrival_order
FROM ranked
GROUP BY session_id
HAVING BOOL_OR(event_order <> arrival_order)
ORDER BY session_id;
