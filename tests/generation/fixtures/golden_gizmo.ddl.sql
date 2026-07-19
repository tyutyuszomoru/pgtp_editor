-- Golden-fixture source DDL for the "create page from table" parity test.
--
-- Run this in a scratch PostgreSQL schema, then in PHP Generator:
--   1. Connect to that database.
--   2. Add data source "pr.gizmo" as a top-level page (accept all defaults —
--      do NOT customize captions, editors, visibility, etc.).
--   3. Save the project (.pgtp).
--   4. Copy the whole <Page ... tableName="pr.gizmo"> ... </Page> block into
--      tests/generation/fixtures/golden_gizmo.page.xml (replacing the
--      self-generated snapshot placeholder there).
--
-- The column set is deliberately representative: serial PK, NOT NULL varchar,
-- text, numeric, boolean, date, timestamp, and a single FK — one of each shape
-- the type_map must handle. Keep this DDL and golden_gizmo.schema.json in sync.

CREATE SCHEMA IF NOT EXISTS pr;

CREATE TABLE pr.category (
    id            serial PRIMARY KEY,
    category_name text
);

CREATE TABLE pr.gizmo (
    id           serial PRIMARY KEY,
    name         varchar(60) NOT NULL,
    description  text,
    qty          numeric(10,2),
    is_active    boolean,
    created_on   date,
    updated_at   timestamp,
    category_id  integer REFERENCES pr.category (id)
);
