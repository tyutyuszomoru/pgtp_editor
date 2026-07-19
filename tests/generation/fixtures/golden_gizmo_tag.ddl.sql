-- Golden-fixture source DDL: a junction/bridge table with a COMPOSITE primary
-- key. Exercises the "PK spans two columns" path — both key columns must be
-- hidden (visible="false") in the Edit/Insert/Compare/MultiEdit representations.
--
-- Capture procedure: same as golden_gizmo.ddl.sql — run this DDL, add data
-- source "pr.gizmo_tag" as a top-level page in PHP Generator with all defaults,
-- save, and paste the <Page ... tableName="pr.gizmo_tag"> block over
-- golden_gizmo_tag.page.xml. Keep this DDL and golden_gizmo_tag.schema.json in
-- sync. (Depends on the pr.gizmo table from golden_gizmo.ddl.sql plus pr.tag.)

CREATE SCHEMA IF NOT EXISTS pr;

CREATE TABLE IF NOT EXISTS pr.tag (
    id       serial PRIMARY KEY,
    tag_name text
);

CREATE TABLE pr.gizmo_tag (
    gizmo_id  integer NOT NULL REFERENCES pr.gizmo (id),
    tag_id    integer NOT NULL REFERENCES pr.tag (id),
    note      text,
    added_on  date,
    PRIMARY KEY (gizmo_id, tag_id)
);
