-- Golden-fixture source DDL: an all-nullable, text-heavy table with NO primary
-- key. Exercises two paths at once:
--   * No PK  -> no column is hidden; every representation lists every column
--               with no visible="false".
--   * Text variety -> varchar(n)/char(n) carry their length as maxLength, text
--               and unknown types (citext) fall back to maxLength="0".
--
-- Capture procedure: same as golden_gizmo.ddl.sql — run this DDL, add data
-- source "pr.memo" as a top-level page in PHP Generator with all defaults, save,
-- and paste the <Page ... tableName="pr.memo"> block over golden_memo.page.xml.
-- Keep this DDL and golden_memo.schema.json in sync.
--
-- NOTE: citext requires `CREATE EXTENSION IF NOT EXISTS citext;` — swap it for
-- text if the extension is unavailable in your scratch DB (adjust the .json to
-- match whatever you actually create).

CREATE SCHEMA IF NOT EXISTS pr;
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE pr.memo (
    title        varchar(200),
    body         text,
    summary      varchar(500),
    tags         varchar(100),
    author_name  varchar(120),
    external_ref char(12),
    slug         citext,
    comments     text
);
