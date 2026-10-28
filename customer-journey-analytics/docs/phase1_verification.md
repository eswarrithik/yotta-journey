# Phase 1 local PostgreSQL verification

Requirements: PostgreSQL 15+ and a PostgreSQL GUI/client connected to a **new, empty** database named `journeyiq`. For example, create the database from the client's database browser or run the SQL below while connected to the server's maintenance database:

```sql
CREATE DATABASE journeyiq;
```

Then connect the SQL client to `journeyiq` and execute the complete `schema.sql` file. Next execute `verify_schema.sql` in the same database. The verification script raises an exception if expected Phase 1 objects, key constraints, or representative indexes are missing; on success it prints the table/view, constraint, and index inventories. The expected tables are the ten core entities plus `cart_items` and `experiment_assignments`; expected views are `cart_order_reconciliation` and `session_identity_exceptions`.

For file-based verification, open `customer-journey-analytics/schema.sql` in the PostgreSQL client and execute the full file, then open and execute `customer-journey-analytics/verify_schema.sql` against that same database. The schema is designed for a fresh database and intentionally does not drop existing tables. To repeat from scratch, create a new empty database rather than dropping a database containing valuable data.

## Additional catalog checks

After `verify_schema.sql` succeeds, the following SQL can be run directly to inspect all constraints and indexes:

```sql
SELECT conrelid::regclass AS table_name, conname, contype
FROM pg_constraint
WHERE connamespace = current_schema()::regnamespace
ORDER BY table_name, contype, conname;

SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = current_schema()
ORDER BY tablename, indexname;
```
