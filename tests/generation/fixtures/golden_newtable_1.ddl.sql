-- REAL parity oracle: this table was added to PHP Generator with all defaults
-- (no manual edits) and golden_newtable_1.page.xml is the verbatim <Page> block
-- it produced. Unlike the self-generated snapshots, this is ground truth — the
-- generator must reproduce it exactly.

CREATE TABLE public.newtable_1 (
	serial serial4 NOT NULL,
	"integer" int4 NULL,
	"comment" varchar NULL,
	"numeric" numeric NULL,
	"boolean" bool NULL,
	CONSTRAINT newtable_1_pk PRIMARY KEY (serial)
);
