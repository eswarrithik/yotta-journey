-- Execute this file after schema.sql using a PostgreSQL SQL client connected to the target database.
-- Raises an exception and fails immediately when required Phase 1 objects/constraints are absent.
DO $verify$
DECLARE
    missing_tables TEXT;
    missing_indexes TEXT;
    actual_count INTEGER;
BEGIN
    SELECT string_agg(expected.table_name, ', ' ORDER BY expected.table_name)
      INTO missing_tables
    FROM (VALUES
        ('customers'), ('sessions'), ('journey_events'), ('pages'), ('products'),
        ('carts'), ('cart_items'), ('orders'), ('support_tickets'), ('experiments'),
        ('experiment_assignments'), ('journey_outcomes')
    ) AS expected(table_name)
    WHERE to_regclass(format('%I.%I', current_schema(), expected.table_name)) IS NULL;
    IF missing_tables IS NOT NULL THEN
        RAISE EXCEPTION 'Missing required tables: %', missing_tables;
    END IF;

    SELECT COUNT(*) INTO actual_count
    FROM information_schema.columns
    WHERE table_schema = current_schema()
      AND table_name IN ('pages', 'products')
      AND column_name IN ('effective_from', 'effective_to');
    IF actual_count <> 4 THEN
        RAISE EXCEPTION 'Expected effective_from/effective_to on pages and products, found % columns', actual_count;
    END IF;

    SELECT COUNT(*) INTO actual_count
    FROM information_schema.table_constraints
    WHERE constraint_schema = current_schema() AND constraint_type = 'PRIMARY KEY';
    IF actual_count <> 12 THEN
        RAISE EXCEPTION 'Expected 12 primary keys, found %', actual_count;
    END IF;

    SELECT COUNT(*) INTO actual_count
    FROM information_schema.table_constraints
    WHERE constraint_schema = current_schema() AND constraint_type = 'FOREIGN KEY';
    IF actual_count < 17 THEN
        RAISE EXCEPTION 'Expected at least 17 foreign keys, found %', actual_count;
    END IF;

    SELECT COUNT(*) INTO actual_count
    FROM information_schema.table_constraints
    WHERE constraint_schema = current_schema() AND constraint_type = 'UNIQUE';
    IF actual_count < 3 THEN
        RAISE EXCEPTION 'Expected bridge/outcome uniqueness constraints, found %', actual_count;
    END IF;

    SELECT COUNT(*) INTO actual_count
    FROM information_schema.views
    WHERE table_schema = current_schema()
      AND table_name IN ('cart_order_reconciliation', 'session_identity_exceptions');
    IF actual_count <> 2 THEN
        RAISE EXCEPTION 'Expected 2 audit views, found %', actual_count;
    END IF;

    SELECT string_agg(expected.index_name, ', ' ORDER BY expected.index_name)
      INTO missing_indexes
    FROM (VALUES
        ('journey_events_session_time_idx'), ('journey_events_ingestion_idx'),
        ('journey_events_type_time_idx'), ('journey_events_properties_gin_idx'),
        ('sessions_channel_device_started_idx'), ('orders_status_time_idx'),
        ('support_tickets_status_created_idx'), ('experiment_assignments_session_time_idx'),
        ('journey_outcomes_type_time_idx')
    ) AS expected(index_name)
    WHERE to_regclass(format('%I.%I', current_schema(), expected.index_name)) IS NULL;
    IF missing_indexes IS NOT NULL THEN
        RAISE EXCEPTION 'Missing required indexes: %', missing_indexes;
    END IF;

    RAISE NOTICE 'JourneyIQ Phase 1 schema verification passed: 12 tables, PK/FK/UQ constraints, indexes, and 2 audit views.';
END
$verify$;

-- Human-readable inventory after the assertion block succeeds.
SELECT table_name, table_type
FROM information_schema.tables
WHERE table_schema = current_schema()
  AND table_name IN (
      'customers','sessions','journey_events','pages','products','carts','cart_items',
      'orders','support_tickets','experiments','experiment_assignments','journey_outcomes',
      'cart_order_reconciliation','session_identity_exceptions'
  )
ORDER BY table_type, table_name;

SELECT conrelid::regclass AS table_name, conname AS constraint_name, contype AS constraint_type
FROM pg_constraint
WHERE connamespace = current_schema()::regnamespace
ORDER BY table_name, constraint_type, constraint_name;

SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = current_schema()
ORDER BY tablename, indexname;
