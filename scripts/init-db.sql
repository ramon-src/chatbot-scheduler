-- =============================================================================
-- SIMPLIFICAPSI - DATABASE BOOTSTRAP (runs once on first Postgres boot)
-- =============================================================================
-- Single source of truth for the SCHEMA is Alembic (`make migrate`).
-- This script only prepares the database so migrations can run:
--   - required extensions
--   - the `simplificapsi` schema
--   - privileges (incl. defaults for tables Alembic will create later)
-- Tables, indexes, triggers and the dev user are NOT created here:
--   - tables/indexes      -> Alembic migrations (`make migrate`)
--   - dev user/seed data  -> `make seed` (scripts/seed_dev.py)
-- =============================================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Schema
CREATE SCHEMA IF NOT EXISTS simplificapsi;

-- Privileges for the application role on the schema and any future objects
GRANT ALL PRIVILEGES ON SCHEMA simplificapsi TO simplificapsi;
ALTER DEFAULT PRIVILEGES IN SCHEMA simplificapsi
    GRANT ALL PRIVILEGES ON TABLES TO simplificapsi;
ALTER DEFAULT PRIVILEGES IN SCHEMA simplificapsi
    GRANT ALL PRIVILEGES ON SEQUENCES TO simplificapsi;
